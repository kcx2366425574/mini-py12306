from py12306.helpers.func import singleton, create_thread_and_run, Const, stay_second


@singleton
class Event:
    """
    处理事件
    """
    # 事件
    KEY_JOB_DESTROY = 'job_destroy'
    KEY_USER_JOB_DESTROY = 'user_job_destroy'
    KEY_USER_LOADED = 'user_loaded'

    def job_destroy(self, data=None):
        # 停止查询任务
        if data is None:
            data = {}
        from py12306.query.query import Query

        job = Query.job_by_name(data.get('name'))
        if job:
            job.destroy()

    def user_loaded(self, data=None):
        # 用户初始化完成
        if data is None:
            data = {}
        from py12306.query.query import Query

        query = Query.wait_for_ready()
        for job in query.jobs:
            if job.account_key == data.get('key'):
                create_thread_and_run(job, 'check_passengers', Const.IS_TEST)  # 检查乘客信息 防止提交订单时才检查
                stay_second(1)

    def user_job_destroy(self, data=None):
        if data is None:
            data = {}

        from py12306.user.user import User
        user = User.get_user(data.get('key'))
        if user:
            user.destroy()
