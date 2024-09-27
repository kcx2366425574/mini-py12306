# -*- coding: utf-8 -*-
from time import sleep

from py12306.app import App
from py12306.log.common_log import CommonLog
from py12306.query.query import Query
from py12306.user.user import User
from py12306.web.web import Web


def main():
    CommonLog.print_welcome()
    App.run()
    CommonLog.print_configs()
    App.did_start()

    App.run_check()
    Query.check_before_run()
    print('开始运行...',)

    # ####### 运行任务

    # 运行web后台管理页面
    Web.run()

    # 检测用户登录状态
    User.run()

    # 余票查询
    Query.run()
    while True:
        sleep(10000)


if __name__ == '__main__':
    main()
