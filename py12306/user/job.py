import base64
import json
import os
import pickle
import re
import time

from py12306.app import app_available_check
from py12306.config import Config
from py12306.helpers.api import (
    API_AUTH_QRCODE_CHECK, API_USER_LOGIN, API_AUTH_QRCODE_BASE64_DOWNLOAD, API_AUTH_UAMTK,
    API_AUTH_UAMAUTHCLIENT, API_USER_INFO, API_BASE_LOGIN, API_USER_LOGIN_CHECK, API_USER_PASSENGERS, API_INITDC_URL
)
from py12306.helpers.event import Event
from py12306.helpers.func import (
    time_int, get_interval_num, stay_second, is_number, array_dict_find_by_key_value,
    dict_find_key_by_value
)
from py12306.helpers.notification import Notification
from py12306.helpers.qrcode import print_qrcode
from py12306.helpers.request import Request
from py12306.helpers.type import UserType
from py12306.log.common_log import CommonLog
from py12306.log.order_log import OrderLog
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

    def update_user(self):
        from py12306.user.user import User
        self.user = User()
        self.load_user()

    def load_user(self):
        cookie_path = self.get_cookie_path()

        if os.path.exists(cookie_path):
            with open(self.get_cookie_path(), 'rb') as f:
                cookie = pickle.load(f)
                self.cookie = True
                self.session.cookies.update(cookie)
                return self.did_loaded_user()
        return None

    def check_user_is_login(self):
        retry = 0
        while retry < Config().REQUEST_MAX_RETRY:
            retry += 1
            response = self.session.get(API_USER_LOGIN_CHECK)
            is_login = response.json().get('data.is_login', False) == 'Y'
            if is_login:
                self.save_user()
                self.set_last_heartbeat()
                return self.get_user_info()
                # 检测应该是不会维持状态，这里再请求下个人中心看有没有用，01-10 看来应该是没用  01-22 有时拿到的状态 是已失效的再加上试试
            time.sleep(get_interval_num(self.sleep_interval))
        return False

    def can_access_passengers(self):
        retry = 0
        while retry < Config().REQUEST_MAX_RETRY:
            retry += 1
            response = self.session.post(API_USER_PASSENGERS)
            result = response.json()
            if result.get('data.normal_passengers'):
                return True
            else:
                wait_time = get_interval_num(self.sleep_interval)
                UserLog.add_quick_log(
                    UserLog.MESSAGE_TEST_GET_USER_PASSENGERS_FAIL.format(
                        result.get('messages', CommonLog.MESSAGE_RESPONSE_EMPTY_ERROR), wait_time)).flush()
                stay_second(wait_time)
        return False

    def did_loaded_user(self):
        """
        恢复用户成功
        :return:
        """
        UserLog.add_quick_log(UserLog.MESSAGE_LOADED_USER.format(self.user_name)).flush()
        if self.check_user_is_login() and self.can_access_passengers():
            UserLog.add_quick_log(UserLog.MESSAGE_LOADED_USER_SUCCESS.format(self.user_name)).flush()
            UserLog.print_welcome_user(self)
            self.user_did_load()
            return True
        else:
            UserLog.add_quick_log(UserLog.MESSAGE_LOADED_USER_BUT_EXPIRED).flush()
            self.set_last_heartbeat(0)
            return False

    def user_did_load(self):
        """
        用户已经加载成功
        :return:
        """
        self.is_ready = True
        if self.user_loaded:
            return
        self.user_loaded = True
        Event().user_loaded({'key': self.key})  # 发布通知

    def run(self):
        # load user
        self.update_user()
        self.start()

    def is_first_time(self):
        return not os.path.exists(self.get_cookie_path())

    def get_name(self):
        return self.info.get('user_name', '')

    def check_heartbeat(self):
        # 心跳检测
        if self.last_heartbeat and (time_int() - self.last_heartbeat) < Config().USER_HEARTBEAT_INTERVAL:
            return True
        # 只有主节点才能走到这
        if self.is_first_time() or not self.check_user_is_login() or not self.can_access_passengers():
            if not self.load_user() and not self.handle_login():
                return

        self.user_did_load()
        message = UserLog.MESSAGE_USER_HEARTBEAT_NORMAL.format(self.get_name(), Config().USER_HEARTBEAT_INTERVAL)
        UserLog.add_quick_log(message).flush()

    def start(self):
        """
        检测心跳
        :return:
        """
        while self.is_alive:
            app_available_check()

            self.check_heartbeat()

            stay_second(self.check_interval)

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
        response = self.session.post(API_BASE_LOGIN.get('url') + '?' + post_data)
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
            except Exception:
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

    def wait_for_ready(self):
        if self.is_ready:
            return self
        UserLog.add_quick_log(UserLog.MESSAGE_WAIT_USER_INIT_COMPLETE.format(self.retry_time)).flush()
        stay_second(self.retry_time)
        return self.wait_for_ready()

    def destroy(self):
        """
        退出用户
        :return:
        """
        UserLog.add_quick_log(UserLog.MESSAGE_USER_BEING_DESTROY.format(self.user_name)).flush()
        self.is_alive = False

    def get_user_passengers(self):
        if self.passengers:
            return self.passengers
        response = self.session.post(API_USER_PASSENGERS)
        result = response.json()
        if result.get('data.normal_passengers'):
            self.passengers = result.get('data.normal_passengers')
            # 将乘客写入到文件
            with open(Config().USER_PASSENGERS_FILE % self.user_name, 'w', encoding='utf-8') as f:
                f.write(json.dumps(self.passengers, indent=4, ensure_ascii=False))
            return self.passengers
        else:
            wait_time = get_interval_num(self.sleep_interval)
            UserLog.add_quick_log(
                UserLog.MESSAGE_GET_USER_PASSENGERS_FAIL.format(
                    result.get('messages', CommonLog.MESSAGE_RESPONSE_EMPTY_ERROR), wait_time)).flush()
            stay_second(wait_time)
            return self.get_user_passengers()

    def get_passengers_by_members(self, members):
        """
        获取格式化后的乘客信息
        :param members:
        :return:
        [{
            name: '项羽',
            type: 1,
            id_card: 0000000000000000000,
            type_text: '成人',
            enc_str: 'aaaaaa'
        }]
        """
        self.get_user_passengers()
        results = []
        for member in members:
            is_member_code = is_number(member)
            if not is_member_code:
                if member[0] == "*":
                    audlt = 1
                    member = member[1:]
                else:
                    audlt = 0
                child_check = array_dict_find_by_key_value(results, 'name', member)
            if not is_member_code and child_check:
                new_member = child_check.copy()
                new_member['type'] = UserType.CHILD
                new_member['type_text'] = dict_find_key_by_value(UserType.dicts, int(new_member['type']))
            else:
                if is_member_code:
                    passenger = array_dict_find_by_key_value(self.passengers, 'code', member)
                else:
                    passenger = array_dict_find_by_key_value(self.passengers, 'passenger_name', member)
                    if audlt:
                        passenger['passenger_type'] = UserType.ADULT
                if not passenger:
                    UserLog.add_quick_log(
                        UserLog.MESSAGE_USER_PASSENGERS_IS_INVALID.format(self.user_name, member)).flush()
                    return False
                new_member = {
                    'name': passenger.get('passenger_name'),
                    'id_card': passenger.get('passenger_id_no'),
                    'id_card_type': passenger.get('passenger_id_type_code'),
                    'mobile': passenger.get('mobile_no'),
                    'type': passenger.get('passenger_type'),
                    'type_text': dict_find_key_by_value(UserType.dicts, int(passenger.get('passenger_type'))),
                    'enc_str': passenger.get('allEncStr')
                }
            results.append(new_member)

        return results

    def request_init_dc_page(self):
        """
        请求下单页面 拿到 token
        :return:
        """
        data = {'_json_att': ''}
        response = self.session.post(API_INITDC_URL, data)
        html = response.text
        token = re.search(r'var globalRepeatSubmitToken = \'(.+?)\'', html)
        form = re.search(r'var ticketInfoForPassengerForm *= *(\{.+\})', html)
        order = re.search(r'var orderRequestDTO *= *(\{.+\})', html)
        # 系统忙，请稍后重试
        if html.find('系统忙，请稍后重试') != -1:
            OrderLog.add_quick_log(OrderLog.MESSAGE_REQUEST_INIT_DC_PAGE_FAIL).flush()  # 重试无用，直接跳过
            return False, False, html
        try:
            self.global_repeat_submit_token = token.groups()[0]
            self.ticket_info_for_passenger_form = json.loads(form.groups()[0].replace("'", '"'))
            self.order_request_dto = json.loads(order.groups()[0].replace("'", '"'))
        except Exception:
            return False, False, html

        slide_val = re.search(r"var if_check_slide_passcode.*='(\d?)'", html)
        is_slide = False
        if slide_val:
            is_slide = int(slide_val[1]) == 1
        return True, is_slide, html

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
