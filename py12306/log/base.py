import sys

from py12306.config import Config
from py12306.helpers.func import is_main_thread, current_thread_id, Const


class BaseLog:
    logs = []
    thread_logs = {}
    quick_log = []

    @classmethod
    def add_log(cls, content=''):
        self = cls()
        if is_main_thread():
            self.logs.append(content)
        else:
            tmp_log = self.thread_logs.get(current_thread_id(), [])
            tmp_log.append(content)
            self.thread_logs[current_thread_id()] = tmp_log
        return self

    @classmethod
    def flush(cls, sep='\n', end='\n', file=None, exit_flag=False):
        self = cls()
        logs = self.get_logs()
        # 输出到文件
        if file is None and Config().OUT_PUT_LOG_TO_FILE_ENABLED and not Const.IS_TEST:
            file = open(Config().OUT_PUT_LOG_TO_FILE_PATH, 'a', encoding='utf-8')
        if not file:
            file = None

        print(*logs, sep=sep, end=end, file=file)
        self.empty_logs(logs)
        if exit_flag:
            sys.exit()

    def get_logs(self):
        if self.quick_log:
            logs = self.quick_log
        else:
            if is_main_thread():
                logs = self.logs
            else:
                logs = self.thread_logs.get(current_thread_id())
        return logs

    def empty_logs(self, logs=None):
        if self.quick_log:
            self.quick_log = []
        else:
            if is_main_thread():
                self.logs = []
            else:
                if logs and self.thread_logs.get(current_thread_id()):
                    del self.thread_logs[current_thread_id()]

    @classmethod
    def add_quick_log(cls, content=''):
        self = cls()
        self.quick_log.append(content)
        return self

    def notification(self, title, content=''):
        # if sys.platform == 'darwin': # 不太友好 先关闭，之前没考虑到 mac 下会请求权限
        #     os.system( 'osascript -e \'tell app "System Events" to display notification "{content}" with title "{title}"\''.format(
        #             title=title, content=content))
        pass
