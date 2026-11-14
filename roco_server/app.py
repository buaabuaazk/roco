"""FastAPI 本地 API 和 SSE 事件流。"""
import asyncio
from contextlib import asynccontextmanager
import json
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .service import BusyError, SessionManager
from .data_updates import DataUpdates
from roco_data import RocoTools
from .battle_setup import PetSetup, MatchupInput, panel, pet_skills, matchup, level_editable, pet_image_url
from .buffs import BUFF_CATALOG


class SessionInput(BaseModel):
    model: str | None = Field(default=None, max_length=200)


class QuestionInput(BaseModel):
    question: str = Field(min_length=1, max_length=4000)

    @field_validator('question')
    @classmethod
    def clean(cls, value):
        if not value.strip():
            raise ValueError('请输入问题')
        return value.strip()


def create_app(manager=None):
    @asynccontextmanager
    async def lifespan(app):
        app.state.manager = manager or SessionManager()
        app.state.updates = DataUpdates(app.state.manager)
        yield
        app.state.manager.close()

    app = FastAPI(title='Roco Debug API', lifespan=lifespan)
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]'])

    @app.exception_handler(BusyError)
    async def busy_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=409)

    @app.exception_handler(KeyError)
    async def missing_error(request, error):
        return JSONResponse({'detail': '会话或记录不存在，请重新打开会话'}, status_code=404)

    @app.exception_handler(OSError)
    async def file_error(request, error):
        return JSONResponse({'detail': '本地资料或日志访问失败，请检查服务端终端'}, status_code=500)

    @app.exception_handler(ValueError)
    async def value_error(request, error):
        return JSONResponse({'detail': str(error)}, status_code=400)

    @app.get('/api/config')
    def config(request: Request):
        return request.app.state.manager.config()

    @app.get('/api/damage/skills')
    def damage_skills(request: Request):
        queries = request.app.state.manager.queries
        return [{'skill_id': skill['skill_id'], 'name': skill['name'], 'element': skill.get('element'),
                 'damage_class': skill.get('damage_class'), 'power': skill['power'], 'description': skill.get('desc', '')}
                for skill in sorted(queries.skills.values(), key=lambda row: (row['name'], row['skill_id']))
                if skill.get('category') == '攻击' and type(skill.get('power')) in (int, float)]

    @app.get('/api/damage/buffs')
    def damage_buffs():
        return BUFF_CATALOG

    @app.get('/api/damage/pets')
    def damage_pets(request: Request):
        return [{'pet_id': pet['pet_id'], 'name': pet['title'], 'types': pet['profile']['types'],
                 'level_editable': level_editable(pet), 'image_url': pet_image_url(pet)}
                for pet in sorted(request.app.state.manager.queries.pets.values(), key=lambda row: (row['title'], row['pet_id']))]

    @app.get('/api/damage/pets/{pet_id}/skills')
    def damage_pet_skills(pet_id: int, request: Request):
        return pet_skills(request.app.state.manager.queries, pet_id)

    @app.post('/api/damage/panel')
    def damage_panel(body: PetSetup, request: Request):
        return panel(request.app.state.manager.queries, body)

    @app.post('/api/damage/matchup')
    def damage_matchup(body: MatchupInput, request: Request):
        return matchup(request.app.state.manager.queries, body)

    @app.post('/api/damage/calculate')
    def damage_calculate(body: dict, request: Request):
        answer = RocoTools(request.app.state.manager.queries).execute('calculate_damage', body)
        if answer['status'] != 'ok':
            return JSONResponse({'detail': answer.get('message', '伤害计算失败')}, status_code=422)
        return answer['data']

    @app.get('/api/sessions')
    def sessions(request: Request):
        return request.app.state.manager.list()

    @app.post('/api/sessions')
    def new_session(body: SessionInput, request: Request):
        return request.app.state.manager.create(body.model)

    @app.get('/api/sessions/{session_id}')
    def session(session_id: str, request: Request):
        return request.app.state.manager.get(session_id).snapshot()

    @app.post('/api/sessions/{session_id}/reset')
    def reset(session_id: str, request: Request):
        current = request.app.state.manager.get(session_id)
        current.reset()
        return current.snapshot()

    @app.post('/api/sessions/{session_id}/runs')
    def ask(session_id: str, body: QuestionInput, request: Request):
        return {'run_id': request.app.state.manager.start(session_id, body.question)}

    @app.post('/api/data/reload')
    def reload_data(request: Request):
        if request.app.state.manager.data_updating:
            raise BusyError('数据正在更新，请等待完成')
        return request.app.state.manager.reload_data()

    @app.get('/api/data/status')
    def data_status(request: Request):
        return request.app.state.updates.snapshot()

    @app.post('/api/data/check')
    def data_check(request: Request):
        return request.app.state.updates.start('check')

    @app.post('/api/data/update')
    def data_update(request: Request):
        return request.app.state.updates.start('update')

    @app.get('/api/sessions/{session_id}/runs/{run_id}/events')
    async def events(session_id: str, run_id: str, request: Request):
        current = request.app.state.manager.get(session_id)
        try:
            cursor = max(0, int(request.headers.get('last-event-id', '0')))
        except ValueError:
            cursor = 0
        current.events(run_id, cursor)

        async def stream():
            nonlocal cursor
            last_ping = 0
            while True:
                if await request.is_disconnected():
                    break
                records, done = current.events(run_id, cursor)
                for record in records:
                    cursor = record['sequence']
                    yield f'id: {cursor}\ndata: {json.dumps(record, ensure_ascii=False)}\n\n'
                if done:
                    break
                last_ping += 1
                if last_ping % 50 == 0:
                    yield ': heartbeat\n\n'
                await asyncio.sleep(0.2)

        return StreamingResponse(stream(), media_type='text/event-stream',
                                 headers={'Cache-Control': 'no-cache', 'X-Accel-Buffering': 'no'})

    dist = Path(__file__).resolve().parents[1] / 'web/dist'
    if dist.exists():
        app.mount('/', StaticFiles(directory=dist, html=True), name='web')
    return app


app = create_app()
