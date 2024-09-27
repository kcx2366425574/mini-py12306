# -*- coding: utf-8 -*-
import re
from os import path

from py12306.helpers.func import singleton

# 12306 账号


@singleton
class Config:
    IS_DEBUG = False

    USER_ACCOUNTS = []
    # 查询任务
    QUERY_JOBS = []
    # 查询间隔
    QUERY_INTERVAL = 1
    # 查询重试次数
    REQUEST_MAX_RETRY = 5
    # 用户心跳检测间隔
    USER_HEARTBEAT_INTERVAL = 120
    # 多线程查询
    QUERY_JOB_THREAD_ENABLED = 0
    # 打码平台账号
    AUTO_CODE_PLATFORM = ''
    # 用户打码平台地址
    API_USER_CODE_QCR_API = ''
    AUTO_CODE_ACCOUNT = {'user': '', 'pwd': ''}
    # 输出日志到文件
    OUT_PUT_LOG_TO_FILE_ENABLED = 0
    OUT_PUT_LOG_TO_FILE_PATH = 'runtime/12306.log'

    SEAT_TYPES = {'特等座': 25, '商务座': 32, '一等座': 31, '二等座': 30, '软卧': 23, '硬卧': 28, '硬座': 29, '无座': 26, }

    ORDER_SEAT_TYPES = {'特等座': 'P', '商务座': 9, '一等座': 'M', '二等座': 'O', '软卧': 4, '硬卧': 3, '硬座': 1, '无座': 1}

    PROJECT_DIR = path.dirname(path.dirname(path.abspath(__file__))) + '/'

    # Query
    RUNTIME_DIR = PROJECT_DIR + 'runtime/'
    QUERY_DATA_DIR = RUNTIME_DIR + 'query/'
    USER_DATA_DIR = RUNTIME_DIR + 'user/'
    USER_PASSENGERS_FILE = RUNTIME_DIR + 'user/%s_passengers.json'

    STATION_FILE = PROJECT_DIR + 'data/stations.txt'
    CONFIG_FILE = PROJECT_DIR + 'env.py'

    # 语音验证码
    NOTIFICATION_BY_VOICE_CODE = 0
    NOTIFICATION_VOICE_CODE_TYPE = ''
    NOTIFICATION_VOICE_CODE_PHONE = ''
    NOTIFICATION_API_APP_CODE = ''

    # 钉钉配置
    DINGTALK_ENABLED = 0
    DINGTALK_WEBHOOK = ''

    # Telegram推送配置
    TELEGRAM_ENABLED = 0
    TELEGRAM_BOT_API_URL = ''

    # Bark 推送配置
    BARK_ENABLED = 0
    BARK_PUSH_URL = ''

    # ServerChan和PushBear配置
    SERVERCHAN_ENABLED = 0
    SERVERCHAN_KEY = '8474-ca071ADSFADSF'
    PUSHBEAR_ENABLED = 0
    PUSHBEAR_KEY = 'SCUdafadsfasfdafdf45234234234'

    # 邮箱配置
    EMAIL_ENABLED = 0
    EMAIL_SENDER = ''
    EMAIL_RECEIVER = ''
    EMAIL_SERVER_HOST = ''
    EMAIL_SERVER_USER = ''
    EMAIL_SERVER_PASSWORD = ''

    WEB_ENABLE = 0
    WEB_USER = {}
    WEB_PORT = 8080
    WEB_ENTER_HTML_PATH = PROJECT_DIR + 'py12306/web/static/index.html'

    CACHE_RAIL_ID_ENABLED = 0
    RAIL_EXPIRATION = ''
    RAIL_DEVICEID = ''

    # Default time out
    TIME_OUT_OF_REQUEST = 5

    envs = []

    def __init__(self):
        self.init_envs()

    def init_envs(self):
        self.envs = EnvLoader.load_with_file(self.CONFIG_FILE)
        self.update_configs(self.envs)

    def update_configs(self, envs):
        for key, value in envs:
            setattr(self, key, value)

    @staticmethod
    def is_cache_rail_id_enabled():
        return Config().CACHE_RAIL_ID_ENABLED


class EnvLoader:
    envs = []

    def __init__(self):
        self.envs = []

    @classmethod
    def load_with_file(cls, file):
        self = cls()
        if path.exists(file):
            env_content = open(file, encoding='utf8').read()
            content = re.sub(r'^([A-Z]+)_', r'self.\1_', env_content, flags=re.M)
            exec(content)
        return self.envs

    def __setattr__(self, key, value):
        super().__setattr__(key, value)
        if re.search(r'^[A-Z]+_', key):
            self.envs.append(([key, value]))
