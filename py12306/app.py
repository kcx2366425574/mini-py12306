# -*- coding: utf-8 -*-
import datetime
import os
import signal
import sys
from time import sleep

from py12306.config import Config
from py12306.helpers.notification import Notification

from py12306.helpers.func import time_now, singleton, touch_file, Const
from py12306.log.common_log import CommonLog
from py12306.log.order_log import OrderLog


def app_available_check():

    """检测12306是否可用"""

    now = time_now()
    if now.weekday() == 1 and (now.hour > 23 and now.minute > 30 or now.hour < 5):
        CommonLog.add_quick_log(CommonLog.MESSAGE_12306_IS_CLOSED.format(time_now())).flush()
        open_time = datetime.datetime(now.year, now.month, now.day, 5)
        if open_time < now:
            open_time += datetime.timedelta(1)
        sleep((open_time - now).seconds)
    elif 1 < now.hour < 5:
        CommonLog.add_quick_log(CommonLog.MESSAGE_12306_IS_CLOSED.format(time_now())).flush()
        open_time = datetime.datetime(now.year, now.month, now.day, 5)
        sleep((open_time - now).seconds)


@singleton
class App:
    """
    程序主类
    """

    @classmethod
    def run(cls):
        self = cls()
        self.register_sign()

    @classmethod
    def did_start(cls):
        from py12306.helpers.station import Station
        Station()  # 防止多线程时初始化出现问题

    def register_sign(self):

        signs = [signal.SIGINT, signal.SIGTERM]
        for sign in signs:
            signal.signal(sign, self.handler_exit)

    def handler_exit(self, *args, **kwargs):
        """
        程序退出
        :param args:
        :param kwargs:
        :return:
        """
        sys.exit()

    @classmethod
    def check_auto_code(cls):
        if Config().AUTO_CODE_PLATFORM == 'free' or Config().AUTO_CODE_PLATFORM == 'user':
            return True
        if not Config().AUTO_CODE_ACCOUNT.get('user') or not Config().AUTO_CODE_ACCOUNT.get('pwd'):
            return False
        return True

    @classmethod
    def check_user_account_is_empty(cls):
        if Config().USER_ACCOUNTS:
            for account in Config().USER_ACCOUNTS:
                if account:
                    return False
        return True

    @staticmethod
    def check_data_dir_exists():
        os.makedirs(Config().QUERY_DATA_DIR, exist_ok=True)
        os.makedirs(Config().USER_DATA_DIR, exist_ok=True)
        touch_file(Config().OUT_PUT_LOG_TO_FILE_PATH)

    @classmethod
    def test_send_notifications(cls):
        test_send_msg = "测试发送信息"
        test_by_12306 = "By py12306"
        if Config().NOTIFICATION_BY_VOICE_CODE:  # 语音通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_VOICE_CODE).flush()
            if Config().NOTIFICATION_VOICE_CODE_TYPE == 'dingxin':
                voice_content = {'left_station': '广州', 'arrive_station': '深圳', 'set_type': '硬座', 'orderno': 'E123542'}
            else:
                voice_content = OrderLog.MESSAGE_ORDER_SUCCESS_NOTIFICATION_OF_VOICE_CODE_CONTENT.format('北京', '深圳')
            Notification.voice_code(Config().NOTIFICATION_VOICE_CODE_PHONE, '张三', voice_content)
        if Config().EMAIL_ENABLED:  # 邮件通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_EMAIL).flush()
            Notification.send_email(Config().EMAIL_RECEIVER, '测试发送邮件', test_by_12306)

        if Config().DINGTALK_ENABLED:  # 钉钉通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_DINGTALK).flush()
            Notification.dingtalk_webhook(test_send_msg)

        if Config().TELEGRAM_ENABLED:  # Telegram通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_TELEGRAM).flush()
            Notification.send_to_telegram(test_send_msg)

        if Config().SERVERCHAN_ENABLED:  # ServerChan通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_SERVER_CHAN).flush()
            Notification.server_chan(Config().SERVERCHAN_KEY, test_send_msg, test_by_12306)

        if Config().PUSHBEAR_ENABLED:  # PushBear通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_PUSH_BEAR).flush()
            Notification.push_bear(Config().PUSHBEAR_KEY, test_send_msg, test_by_12306)

        if Config().BARK_ENABLED:  # Bark通知
            CommonLog.add_quick_log(CommonLog.MESSAGE_TEST_SEND_PUSH_BARK).flush()
            Notification.push_bark(test_send_msg)

    @classmethod
    def run_check(cls):
        """
        待优化
        :return:
        """
        cls.check_data_dir_exists()
        if not cls.check_user_account_is_empty() and not cls.check_auto_code():
            CommonLog.add_quick_log(CommonLog.MESSAGE_CHECK_AUTO_CODE_FAIL).flush(exit=True, publish=False)
        if Const.IS_TEST_NOTIFICATION:
            cls.test_send_notifications()


# Expand
class Dict(dict):
    def get(self, key, default=None, sep='.'):
        keys = key.split(sep)
        for i, key in enumerate(keys):
            try:
                value = self[key]
                if len(keys[i + 1:]) and isinstance(value, Dict):
                    return value.get(sep.join(keys[i + 1:]), default=default, sep=sep)
                return value
            except Exception:
                return self.dict_to_dict(default)

    def __getitem__(self, k):
        return self.dict_to_dict(super().__getitem__(k))

    @staticmethod
    def dict_to_dict(value):
        return Dict(value) if isinstance(value, dict) else value
