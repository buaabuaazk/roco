"""喵喵采集快捷入口，使用统一的精灵采集流程。"""
import sys
from collect_pets import main


if __name__ == '__main__':
    sys.argv[1:1] = ['--ids', '3001']
    main()
