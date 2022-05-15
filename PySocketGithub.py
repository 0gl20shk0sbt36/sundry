import socket
from warnings import warn
from github import Github
from github.GithubException import UnknownObjectException
from datetime import date


class GithubConnectionError(EOFError):

    def __init__(self, str_):
        self.str = str_

    def __str__(self):
        return self.str


class FromGithubGetIpTimeoutError(EOFError):

    def __str__(self):
        return '连接超时'


class ValueWarning(Warning):

    def __init__(self, warning):
        self.warning = warning

    def __str__(self):
        return self.warning


def from_github_get_repo(full_name_or_id, login_or_token=None, g=None, _all=False):
    _g = g is not None
    if g is None:
        g = Github(login_or_token)
    try:
        repo = g.get_repo(full_name_or_id)
    except UnknownObjectException:
        raise GithubConnectionError('仓库连接失败')
    if not _all:
        if _g:
            return repo
        else:
            return g, repo
    else:
        return g, repo


def from_github_get_file(path, full_name_or_id=None, login_or_token=None, g=None, repo=None, _all=False):
    _repo = repo is not None
    _g = g is not None
    if repo is None:
        if g is None:
            g, repo = from_github_get_repo(full_name_or_id, login_or_token=login_or_token, g=g, _all=True)
    try:
        file = repo.get_contents(path)
    except UnknownObjectException:
        raise GithubConnectionError('文件连接失败')
    if not _all:
        if _repo:
            return file
        elif _g:
            return repo, file
        else:
            return g, repo, file
    else:
        return g, repo, file


def from_github_get_ip(path=None, full_name_or_id=None, login_or_token=None, g=None, repo=None, file=None, _all=False):
    _file = file is not None
    _repo = repo is not None
    _g = g is not None
    if file is None:
        g, repo, file = from_github_get_file(path, full_name_or_id, login_or_token, g, repo, True)
    ip, port = str(file.decoded_content, 'utf-8').split(':')
    if not _all:
        if _file:
            return ip, int(port)
        elif _repo:
            return file, ip, int(port)
        elif _g:
            return repo, file, ip, int(port)
        else:
            return g, repo, file, ip, int(port)
    else:
        return g, repo, file, ip, int(port)


class CLIENT(socket.socket):

    def __init__(
            self,
            path,
            full_name_or_id,
            login_or_token,
            get_path=None,
            get_port=None,
            password=None,
            timeout=None,
            _print=False
    ):
        """客户端类

        :param login_or_token: GitHub令牌
        :param full_name_or_id: GitHub仓库名称
        :param path: 服务端连接地址存放文件路径
        :param get_path: 在服务端连接地址存放文件内的连接地址无效时，将自身地址放在Github中，
                         在服务端上线后连接，获取服务端连接地址。本变量为存放客户端连接地址的
                         文件路径
        :param get_port: 连接地址端口
        :param password: 在服务端连接时进行数据交换进行验证时的秘钥，可以是bytes或可调用对象，
                         接受到的数据将作为参数传入，如果返回值为True，则验证通过，否则继续等
                         待连接
        :param timeout: 设置连接超时时间
        """
        self.get_path = get_path
        self.get_port = get_port
        self.password = password
        self._print = _print
        if timeout is None:
            warn('_time 的值为 None, 这会导致程序无限制等待下去', ValueWarning)
        self._time = timeout
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.g, self.repo, self.file, self.ip, self.port = from_github_get_ip(
                    path, full_name_or_id, login_or_token)
        while True:
            try:
                self.ip, self.port = from_github_get_ip(file=self.file)
                if self._print:
                    print('当前获取的服务端连接地址为：', (str(self.ip),  self.port))
                self.connect((self.ip, self.port))
                if self._print:
                    print('连接成功')
                break
            except (TimeoutError, ConnectionRefusedError):
                if self._print:
                    print('服务端未上线')
                try:
                    self.__from_github_get_ip()
                except socket.timeout:
                    raise FromGithubGetIpTimeoutError()

    def __del__(self):
        self.close()

    def __from_github_get_ip(self):
        try:
            file = self.repo.get_contents(self.get_path)
            self.repo.update_file(file.path, str(date.today(
            )), f'{socket.gethostbyname(socket.gethostname())}:{self.get_port}', file.sha)
        except UnknownObjectException:
            self.repo.create_file(
                self.get_path, str(
                    date.today()), f'{socket.gethostbyname(socket.gethostname())}:{self.get_port}')
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', self.get_port))
        s.listen(1)
        s.settimeout(self._time)
        while True:
            conn, addr = s.accept()
            n = conn.recv(1024)
            if callable(self.password) and not self.password(n):
                continue
            elif self.password is not None and n != self.password:
                continue
            conn.close()
            s.close()
            self.ip, self.port = addr
            return


class SERVER(socket.socket):

    def __init__(
            self,
            path,
            full_name_or_id,
            login_or_token,
            port,
            password=None,
            timeout=None,
            _print=False
    ):
        """服务类

        :param login_or_token: GitHub令牌
        :param full_name_or_id: GitHub仓库名称
        :param path: 服务端连接地址存放文件路径
        :param port: 端口
        :param password: 在服务端连接时进行数据交换进行验证时的秘钥，可以是bytes或可调用对象，
                         对象被调用的返回值将作为数据发送
        :param timeout: 设置连接超时时间
        """
        if timeout is None:
            warn('_time 的值为 None, 这会导致程序无限制等待下去', ValueWarning)
        super().__init__(socket.AF_INET, socket.SOCK_STREAM)
        self.bind(('', port))
        self.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if _print:
            print('当前连接地址为：', f'{socket.gethostbyname(socket.gethostname())}:{port}')
        g, repo, file = from_github_get_file(path, full_name_or_id, login_or_token)
        repo.update_file(file.path, str(date.today()),
                         f'{socket.gethostbyname(socket.gethostname())}:{port}', file.sha)
        file = from_github_get_file('/'.join(path.split('/')[:-1]), repo=repo)
        n = []
        for i in file:
            if i.type != 'dir' and i.path != path:
                a: list = str(i.decoded_content, 'utf-8').split(':')
                a[1] = int(a[1])
                n.append(tuple(a))
                repo.delete_file(i.path, str(date.today()), i.sha)
        if len(n):
            for i in n:
                if _print:
                    print('正在连接', i)
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(timeout)
                try:
                    s.connect(i)
                    if callable(password):
                        s.send(password())
                    elif password is not None:
                        s.send(password)
                    s.close()
                    if _print:
                        print('连接成功')
                except (socket.timeout, ConnectionRefusedError):
                    if _print:
                        print('连接超时')
        else:
            if _print:
                print('无沉积连接')
        if _print:
            print('服务端正常运行')

    def __del__(self):
        self.close()
