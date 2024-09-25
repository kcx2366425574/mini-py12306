from time import sleep

from py12306.config import Config
from py12306.app import app_available_check
from py12306.helpers.func import (
    singleton, init_interval_by_number, jobs_do, stay_second, create_thread_and_run, Const,
    md5, objects_find_object_by_key_value, get_interval_num
)
from py12306.helpers.request import Request
from py12306.log.query_log import QueryLog
from py12306.query.job import Job
from py12306.helpers.api import API_QUERY_INIT_PAGE


@singleton
class Query:
    """
    余票查询

    """
    jobs = []
    query_jobs = []
    session = {}

    # 查询间隔
    interval = {}
    cluster = None

    is_in_thread = False
    retry_time = 3
    is_ready = False
    api_type = None  # Query api url, Current know value  leftTicket/queryX | leftTicket/queryZ

    def __init__(self):
        self.session = Request()
        self.update_query_interval()
        self.update_query_jobs()
        self.get_query_api_type()

    def update_query_interval(self):
        self.interval = init_interval_by_number(Config().QUERY_INTERVAL)

    def update_query_jobs(self, auto=False):
        self.query_jobs = Config().QUERY_JOBS
        if auto:
            QueryLog.add_quick_log(QueryLog.MESSAGE_JOBS_DID_CHANGED).flush()
            self.refresh_jobs()
            jobs_do(self.jobs, 'check_passengers')

    @classmethod
    def run(cls):
        self = cls()
        app_available_check()
        self.start()

    @classmethod
    def check_before_run(cls):
        self = cls()
        self.init_jobs()
        self.is_ready = True

    def start(self):
        # return # DEBUG
        QueryLog.init_data()
        stay_second(3)
        # 多线程
        while True:
            if Config().QUERY_JOB_THREAD_ENABLED:  # 多线程
                if not self.is_in_thread:
                    self.is_in_thread = True
                    create_thread_and_run(jobs=self.jobs, callback_name='run', wait=Const.IS_TEST)
                if Const.IS_TEST: return
                stay_second(self.retry_time)
            else:
                if not self.jobs: break
                self.is_in_thread = False
                jobs_do(self.jobs, 'run')
                if Const.IS_TEST: return

    def refresh_jobs(self):
        """
        更新任务
        :return:
        """
        allow_jobs = []
        for job in self.query_jobs:
            id = md5(job)
            job_ins = objects_find_object_by_key_value(self.jobs, 'id', id)  # [1 ,2]
            if not job_ins:
                job_ins = self.init_job(job)
                if Config().QUERY_JOB_THREAD_ENABLED:  # 多线程重新添加
                    create_thread_and_run(jobs=job_ins, callback_name='run', wait=Const.IS_TEST)
            allow_jobs.append(job_ins)

        for job in self.jobs:  # 退出已删除 Job
            if job not in allow_jobs: job.destroy()

        QueryLog.print_init_jobs(jobs=self.jobs)

    def init_jobs(self):
        for job in self.query_jobs:
            self.init_job(job)
        QueryLog.print_init_jobs(jobs=self.jobs)

    def init_job(self, job):
        job = Job(info=job, query=self)
        self.jobs.append(job)
        return job

    @classmethod
    def wait_for_ready(cls):
        self = cls()
        if self.is_ready:
            return self
        stay_second(self.retry_time)
        return self.wait_for_ready()

    # @classmethod
    # def job_by_name(cls, name) -> Job:
    #     self = cls()
    #     for job in self.jobs:
    #         if job.job_name == name:
    #             return job
    #     return None

    @classmethod
    def job_by_name(cls, name) -> Job:
        self = cls()
        return objects_find_object_by_key_value(self.jobs, 'job_name', name)

    @classmethod
    def job_by_account_key(cls, account_key) -> Job:
        self = cls()
        return objects_find_object_by_key_value(self.jobs, 'account_key', account_key)

    @classmethod
    def get_query_api_type(cls):
        import re
        self = cls()
        if self.api_type:
            return self.api_type
        response = self.session.get(API_QUERY_INIT_PAGE)
        if response.status_code == 200:
            res = re.search(r'var CLeftTicketUrl = \'(.*)\';', response.text)
            try:
                self.api_type = res.group(1)
            except Exception:
                pass
        if not self.api_type:
            QueryLog.add_quick_log('查询地址获取失败, 正在重新获取...').flush()
            sleep(get_interval_num(self.interval))
        return cls.get_query_api_type()
