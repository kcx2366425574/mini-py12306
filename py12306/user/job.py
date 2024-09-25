import base64
import os
import pickle
import time

from py12306.config import Config
from py12306.helpers.api import (
    API_AUTH_QRCODE_CHECK, API_USER_LOGIN, API_AUTH_QRCODE_BASE64_DOWNLOAD, API_AUTH_UAMTK,
    API_AUTH_UAMAUTHCLIENT, API_USER_INFO, API_BASE_LOGIN
)
from py12306.helpers.func import time_int, get_interval_num
from py12306.helpers.notification import Notification
from py12306.helpers.qrcode import print_qrcode
from py12306.helpers.request import Request
from py12306.log.common_log import CommonLog
from py12306.log.user_log import UserLog
from py12306.order.order import Browser


class UserJob:
    # heartbeat = 60 * 2  # 心跳保持时长
    is_alive = True
    check_interval = 5
    key = None
    user_name = ''
    password = ''
    type = 'qr'
    user = None
    info = {}  # 用户信息
    last_heartbeat = None
    is_ready = False
    user_loaded = False  # 用户是否已加载成功
    passengers = []
    retry_time = 3
    retry_count = 0
    login_num = 0  # 尝试登录次数
    sleep_interval = {'min': 0.1, 'max': 5}

    # Init page
    global_repeat_submit_token = None
    ticket_info_for_passenger_form = None
    order_request_dto = None

    cluster = None
    lock_init_user_time = 3 * 60
    cookie = False

    def __init__(self, info):
        self.session = Request()
        self.session.add_response_hook(self.response_login_check)
        self.key = str(info.get('key'))
        self.user_name = info.get('user_name')
        self.password = info.get('password')
        self.type = info.get('type')

    def response_login_check(self, response, **kwargs):
        if response.json().get('data.noLogin') == 'true':
            # relogin
            self.handle_login(expire=True)

    def handle_login(self, expire=False):
        if expire:
            UserLog.print_user_expired()
        self.is_ready = False
        UserLog.print_start_login(user=self)
        if self.type == 'qr':
            return self.qr_login()
        else:
            return self.pw_login()

    def pw_login(self):
        data = {
            'username': self.user_name,
            'password': self.password,
        }
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/94.0.4606.61 Safari/537.36",
        }
        self.session.headers.update(headers)
        cookies, post_data = Browser().request_init_slide2(self.session, data)
        while not cookies or not post_data:
            cookies, post_data = Browser().request_init_slide2(self.session, data)
        for cookie in cookies:
            self.session.cookies.update({
                   cookie['name']: cookie['value']
            })
        response = self.session.post(API_BASE_LOGIN.get('url')+ '?' + post_data)
        result = response.json()
        if result.get('result_code') == 0:  # 登录成功
            """
            login 获得 cookie uamtk
            auth/uamtk      不请求，会返回 uamtk票据内容为空
            /otn/uamauthclient 能拿到用户名
            """
            new_tk = self.auth_uamtk()
            user_name = self.auth_uamauthclient(new_tk)
            self.update_user_info({'user_name': user_name})
            self.login_did_success()
            return True
        elif result.get('result_code') == 2:  # 账号之内错误
            # 登录失败，用户名或密码为空
            # 密码输入错误
            UserLog.add_quick_log(UserLog.MESSAGE_LOGIN_FAIL.format(result.get('result_message'))).flush()
        else:
            UserLog.add_quick_log(
                UserLog.MESSAGE_LOGIN_FAIL.format(
                    result.get('result_message', result.get('message', CommonLog.MESSAGE_RESPONSE_EMPTY_ERROR)))
            ).flush()

        return False

    @classmethod
    def remove_png(cls, png_path):
        try:
            os.remove(png_path)
        except Exception as e:
            UserLog.add_quick_log('无法删除文件: {}'.format(e)).flush()

    def qr_login(self):
        image_uuid, png_path = self.download_code()
        last_time = time_int()

        # 等待用户扫描，扫描后该接口才会返回 result_code = 2
        while True:
            data = {
                'RAIL_DEVICEID': self.session.cookies.get('RAIL_DEVICEID'),
                'RAIL_EXPIRATION': self.session.cookies.get('RAIL_EXPIRATION'),
                'uuid': image_uuid,
                'appid': 'otn'
            }
            response = self.session.post(API_AUTH_QRCODE_CHECK.get('url'), data)
            result = response.json()
            try:
                result_code = int(result.get('result_code'))
            except:
                if time_int() - last_time > 300:
                    last_time = time_int()
                    image_uuid, png_path = self.download_code()
                continue
            if result_code == 0:
                time.sleep(get_interval_num(self.sleep_interval))
            elif result_code == 1:
                UserLog.add_quick_log('请确认登录').flush()
                time.sleep(get_interval_num(self.sleep_interval))
            elif result_code == 2:
                break
            elif result_code == 3:
                self.remove_png(png_path)
                image_uuid, png_path = self.download_code()
            if time_int() - last_time > 300:
                last_time = time_int()
                image_uuid, png_path = self.download_code()

        self.remove_png(png_path)
        self.session.get(API_USER_LOGIN, allow_redirects=True)
        new_tk = self.auth_uamtk()
        user_name = self.auth_uamauthclient(new_tk)
        self.update_user_info({'user_name': user_name})
        self.session.get(API_USER_LOGIN, allow_redirects=True)
        self.login_did_success()
        return True

    def login_did_success(self):
        """
        用户登录成功
        :return:
        """
        self.login_num += 1
        self.welcome_user()
        self.save_user()
        self.get_user_info()
        self.set_last_heartbeat()
        self.is_ready = True

    def set_last_heartbeat(self, new_time=None):
        cur_time = new_time if new_time is not None else time_int()
        self.last_heartbeat = cur_time

    def get_user_info(self):
        retry = 0
        while retry < Config().REQUEST_MAX_RETRY:
            retry += 1
            response = self.session.get(API_USER_INFO.get('url'))
            result = response.json()
            user_data = result.get('data.userDTO.loginUserDTO')
            if user_data:
                self.update_user_info({**user_data, **{'user_name': user_data.get('name')}})
                self.save_user()
                return True
            time.sleep(get_interval_num(self.sleep_interval))
        return False

    def save_user(self):
        with open(self.get_cookie_path(), 'wb') as f:
            pickle.dump(self.session.cookies, f)

    def get_cookie_path(self):
        return Config().USER_DATA_DIR + self.user_name + '.cookie'

    def welcome_user(self):
        UserLog.print_welcome_user(self)

    def update_user_info(self, info):
        self.info = {**self.info, **info}

    def auth_uamauthclient(self, tk):
        retry = 0
        while retry < Config().REQUEST_MAX_RETRY:
            retry += 1
            response = self.session.post(API_AUTH_UAMAUTHCLIENT.get('url'), {'tk': tk})
            result = response.json()
            if result.get('username'):
                return result.get('username')
        return False

    def auth_uamtk(self):
        retry = 0
        while retry < Config().REQUEST_MAX_RETRY:
            retry += 1
            response = self.session.post(API_AUTH_UAMTK.get('url'), {'appid': 'otn'}, headers={
                'Referer': 'https://kyfw.12306.cn/otn/passport?redirect=/otn/login/userLogin',
                'Origin': 'https://kyfw.12306.cn'
            })
            result = response.json()
            if result.get('newapptk'):
                return result.get('newapptk')
        return False

    def download_code(self):
        try:
            UserLog.add_quick_log(UserLog.MESSAGE_QRCODE_DOWNLOADING).flush()
            # 下载二维码
            response = self.session.post(API_AUTH_QRCODE_BASE64_DOWNLOAD.get('url'), data={'appid': 'otn'})
            result = response.json()
            if result.get('result_code') == '0':
                img_bytes = base64.b64decode(result.get('image'))
                try:
                    os.mkdir(Config().USER_DATA_DIR + '/qrcode')
                except FileExistsError:
                    pass
                png_path = os.path.normpath(Config().USER_DATA_DIR + '/qrcode/%d.png' % time.time())
                # 将二维码写入文件
                with open(png_path, 'wb') as file:
                    file.write(img_bytes)
                    file.close()
                # 显示图片
                if os.name == 'nt':
                    os.startfile(png_path)
                else:
                    print_qrcode(png_path)
                UserLog.add_log(UserLog.MESSAGE_QRCODE_DOWNLOADED.format(png_path)).flush()
                Notification.send_email_with_qrcode(Config().EMAIL_RECEIVER, '你有新的登录二维码啦!', png_path)
                self.retry_count = 0
                return result.get('uuid'), png_path
            raise KeyError('获取二维码失败: {}'.format(result.get('result_message')))
        except Exception as e:
            sleep_time = get_interval_num(self.sleep_interval)
            UserLog.add_quick_log(
                UserLog.MESSAGE_QRCODE_FAIL.format(e, sleep_time)).flush()
            time.sleep(sleep_time)
            self.retry_count += 1
            return self.download_code()


if __name__ == '__main__':
    info = {
        'key': '0',
        'user_name': 'your user name',
        'password': '',
        'type': 'qr'
    }
    job = UserJob(info)
    job.qr_login()
