
from py12306.config import Config
from py12306.helpers.func import singleton, create_thread_and_run, Const
from py12306.log.user_log import UserLog
from py12306.user.job import UserJob


@singleton
class User:
    users = []
    user_accounts = []

    retry_time = 3

    def __init__(self):
        self.user_accounts = Config().USER_ACCOUNTS
        self.interval = Config().USER_HEARTBEAT_INTERVAL

    @classmethod
    def run(cls):
        self = cls()
        self.start()

    def start(self):
        self.init_users()
        UserLog.print_init_users(users=self.users)
        # 多线程维护用户
        create_thread_and_run(jobs=self.users, callback_name='run', wait=Const.IS_TEST)

    def init_users(self):
        for account in self.user_accounts:
            self.init_user(account)

    def init_user(self, info):
        user = UserJob(info=info)
        self.users.append(user)
        return user

    @classmethod
    def is_empty(cls):
        self = cls()
        return not bool(self.users)

    @classmethod
    def get_user(cls, key) -> UserJob:
        self = cls()
        for user in self.users:
            if user.key == key:
                return user
        raise KeyError('用户不存在')

    @classmethod
    def get_passenger_for_members(cls, members, key):
        """
        检测乘客信息
        """
        self = cls()

        for user in self.users:
            assert isinstance(user, UserJob)
            if user.key == key and user.wait_for_ready():
                return user.get_passengers_by_members(members)
