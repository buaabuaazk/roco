"""命令行：python -m roco_agent [问题] [--model 模型ID] [--trace]。"""
import argparse
import json
import sqlite3
import sys

from roco_data import DEFAULT_JSON_DIR, RocoQueries, JsonQueries
from .agent import RocoAgent
from .llm import ChatModel, DEFAULT_MODEL
from .session_log import SessionLog


def main():
    parser = argparse.ArgumentParser(description='Roco 精灵助手：智增增模型与五个本地查询工具')
    parser.add_argument('question', nargs='?', help='省略时进入多轮聊天')
    parser.add_argument('--model', help=f'覆盖 LLM_MODEL_ID；两者均未指定时使用 {DEFAULT_MODEL}')
    parser.add_argument('--data-dir', default=str(DEFAULT_JSON_DIR), help='BWIKI 正式 JSON 目录')
    parser.add_argument('--db', help='显式指定时使用 SQLite 查询库')
    parser.add_argument('--trace', action='store_true', help='显示工具名称、参数和状态')
    parser.add_argument('--json', action='store_true', help='单次提问返回完整结构化结果')
    args = parser.parse_args()
    if args.json and args.question is None:
        parser.error('--json 用于单次提问，请同时提供问题')
    model = None
    try:
        with (RocoQueries(args.db) if args.db else JsonQueries(args.data_dir)) as queries:
            model = ChatModel(args.model)
            logger = SessionLog()
            agent = RocoAgent(model, queries, logger=logger)
            if args.trace:
                print(f'日志：{logger.path}', file=sys.stderr)

            def ask(question):
                answer = agent.ask(question)
                if args.json:
                    print(json.dumps(answer, ensure_ascii=False, indent=4))
                else:
                    print(answer['answer'])
                    if args.trace:
                        print(json.dumps(answer['tool_calls'], ensure_ascii=False, indent=4))
                return 0 if answer['status'] == 'ok' else 2

            if args.question is not None:
                return ask(args.question)
            print('Roco 助手已启动。输入 /reset 清空上下文，/exit 退出。')
            while True:
                try:
                    question = input('\n你：').strip()
                except EOFError:
                    break
                if question == '/exit':
                    break
                if question == '/reset':
                    agent.reset()
                    print('上下文已清空。')
                elif question:
                    print('\n助手：', end='', flush=True)
                    ask(question)
            return 0
    except (ValueError, OSError, sqlite3.Error) as exc:
        print(str(exc), file=sys.stderr)
        return 2
    except KeyboardInterrupt:
        print('\n已退出。', file=sys.stderr)
        return 130
    finally:
        if model is not None:
            model.close()


if __name__ == '__main__':
    raise SystemExit(main())
