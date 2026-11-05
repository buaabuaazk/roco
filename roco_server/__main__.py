"""python -m roco_server：启动本机调试台。"""
import argparse
import uvicorn


def main():
    parser = argparse.ArgumentParser(description='Roco 本地调试台')
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    uvicorn.run('roco_server.app:app', host='127.0.0.1', port=args.port)


if __name__ == '__main__':
    main()
