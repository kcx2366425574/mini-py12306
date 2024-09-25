# -*- coding: utf-8 -*-

from py12306.app import App
from py12306.log.common_log import CommonLog
from py12306.query.query import Query


def main():
    CommonLog.print_welcome()
    App.run()
    CommonLog.print_configs()
    App.did_start()

    App.run_check()
    Query.check_before_run()

    # ####### 运行任务
    # Web.run()
    # User.run()
    # Query.run()
    # while True:
    #     sleep(10000)


if __name__ == '__main__':
    main()
