# -*- coding:utf-8 -*-
# Filename:Renren.py
# 作者：华亮
#

from HTMLParser import HTMLParser
from Queue import Empty, Queue
from re import match
from urllib import urlencode
import os, re, json, sys
import threading, time
import urllib, urllib2, socket
import shelve
from pprint import pprint 
import logging, logging.handlers 

def get_logger(handler = logging.StreamHandler()):
    import logging
    logger = logging.getLogger()
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s')
    handler.setFormatter(formatter)
    logger.addHandler(handler)
    logger.setLevel(logging.NOTSET)
    return logger

logger = get_logger() 
GlobalShelveMutex = threading.Lock() 
TaskListFilename = "TaskList.bin"

# 避免urllib2永远不返回
socket.setdefaulttimeout(30)

    
# 字符串形式的unicode转成真正的字符
def Str2Uni(str):
    import re
    pat = re.compile(r'\\u(\w{4})')
    lst = pat.findall(str)        
    lst.insert(0, '')
    return reduce(lambda x,y: x + unichr(int(y, 16)), lst)    

    
class RenrenRequester:
    '''
    人人访问器
    '''
    LoginUrl = 'http://www.renren.com/PLogin.do'

    def CreateByCookie(self, cookie):
        logger.info("Trying to login by cookie")
        cookieFile = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookieFile)
        self.opener.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.4 (KHTML, like Gecko) Chrome/22.0.1229.92 Safari/537.4'),
                                  ('Cookie', cookie),
                                  ]
        
        req = urllib2.Request(self.LoginUrl)

        try:
            result = self.opener.open(req)
        except:
            logger.error("CreateByCookie Failed", exc_info=True)
            return False

        if not self.__FindInfoWhenLogin(result):
            return False

        return True

    
    # 输入用户和密码的元组
    def Create(self, username, password):
        logger.info("Trying to login by password")
        loginData = {'email':username,
                'password':password,
                'origURL':'',
                'formName':'',
                'method':'',
                'isplogin':'true',
                'submit':'登录'}
        postData = urlencode(loginData)
        cookieFile = urllib2.HTTPCookieProcessor()
        self.opener = urllib2.build_opener(cookieFile)
        self.opener.addheaders = [('User-agent', 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.4 (KHTML, like Gecko) Chrome/22.0.1229.92 Safari/537.4')]
        req = urllib2.Request(self.LoginUrl, postData)
        result = self.opener.open(req)

        if not self.__FindInfoWhenLogin(result):
            return False

        return True

    def __FindInfoWhenLogin(self, result):
        result_url = result.geturl()
        logger.info(result_url)
        
        rawHtml = result.read()        

        # 获取用户id
        useridPattern = re.compile(r'user : {"id" : (\d+?)}')
        try:
            self.userid = useridPattern.search(rawHtml).group(1)              
        except:
            return False
        
        # 查找requestToken        
        pos = rawHtml.find("get_check:'")
        if pos == -1: return False        
        rawHtml = rawHtml[pos + 11:]
        token = match('-\d+', rawHtml)
        if token is None:
            token = match('\d+', rawHtml)
            if token is None: return False
        self.requestToken = token.group()  

        # 查找_rtk
        pos = rawHtml.find("get_check_x:'")
        if pos == -1: return False        
        self._rtk = rawHtml[pos + 13:pos + 13 +8]

        logger.info('Login renren.com successfully.')
        logger.info("userid: %s, token: %s, rtk: %s" % (self.userid, self.requestToken, self._rtk))
        
        self.__isLogin = True      
        return self.__isLogin
    
    def GetRequestToken(self):
        return self.requestToken
    
    def GetUserId(self):
        return self.userid
    
    def Request(self, url, data = None):
        if self.__isLogin:
            if data:
                encodeData = urlencode(data)
                request = urllib2.Request(url, encodeData)
            else:
                request = urllib2.Request(url)

            count = 0
            while True:
                try:
                    count += 1
                    if count > 5:
                        break
                    result = self.opener.open(request)
                    url = result.geturl()
                    rawHtml = result.read()
                    break
                except (socket.timeout, urllib2.URLError):
                    logger.error("Request Timeout", exc_info=True)
                    continue
            return rawHtml, url
        else:
            return None
        
        
class RenrenPostMsg:
    '''
    RenrenPostMsg
        发布人人状态
    '''
    newStatusUrl = 'http://shell.renren.com/322542952/status'
    #'http://status.renren.com/doing/updateNew.do'
    
    def Handle(self, requester, param):
        requestToken, userid, _rtk, msg = param

        statusData = {'content':msg,
                      'hostid':userid,
                    'requestToken':requestToken,
                      '_rtk':_rtk,
                      'channel':'renren'}
        postStatusData = urlencode(statusData)
        
        requester.Request(self.newStatusUrl, statusData)
        
        return True

        
class RenrenPostGroupMsg:
    '''
    RenrenPostGroupMsg
        发布人人小组状态
    '''        
    newGroupStatusUrl = 'http://qun.renren.com/qun/ugc/create/status'
    
    def Handle(self, requester, param):
        requestToken, groupId, msg = param
        statusData = {'minigroupId':groupId,
                    'content':msg,
                    'requestToken':requestToken}
        requester.Request(self.newGroupStatusUrl, statusData)


class RenrenFriendList:
    '''
    RenrenFriendList
        人人好友列表
    '''
    def Handler(self, requester, param):     
        friendUrl = 'http://friend.renren.com/myfriendlistx.do'
        rawHtml, url = requester.Request(friendUrl)
         
        friendInfoPack = re.search(r'var friends=\[(.*?)\];', rawHtml).group(1)        
        friendIdPattern = re.compile(r'"id":(\d+).*?"name":"(.*?)"')
        friendIdList = []
        for id, name in friendIdPattern.findall(friendInfoPack):
            friendIdList.append((id, Str2Uni(name)))
        
        return friendIdList        
    
def DownloadImage(img_url, filename):
    count = 0
    # Retry until we get the right picture.
    while True:
        try:
            # 避免过多的重试
            count += 1
            if count > 5:
                logger.error("Too many times retry.")
                break

            n, msg = urllib.urlretrieve(img_url, filename)
            logger.info(n + " " + str(msg.type))
            if "image" in msg.type: 
                break
        except:
            logger.error("Downloading %s is failed." % filename, exc_info=True)


class RenrenAlbumDownloader2012:
    '''单个相册的下载器
    '''

    class DownloaderThread(threading.Thread):
        def __init__(self, tasks_queue):
            threading.Thread.__init__(self)
            self.queue = tasks_queue

        def run(self):
            try:
                while not self.queue.empty():
                    logger.info("Queue size: %d" % self.queue.qsize())
                    img_url, filename = self.queue.get()

                    logger.info("Downloading %s." % filename)
                    DownloadImage(img_url, filename)
            except: 
                logger.error("Error occured in Downloader.", exc_info=True)

    def __init__(self, requester, userid, path, threadnum):
        self.requester = requester    
        self.threadnum = threadnum
        self.userid = userid
        self.path = path

    def Handler(self):
        self.__DownloadOneAlbum(self.userid, self.path)
        
    def __GetPeopleNameFromHtml(self, rawHtml):
        '''解析html获取人名'''
        peopleNamePattern = re.compile(r'<title>(.*?)</title>')
        # 取得人名
        peopleName = peopleNamePattern.search(rawHtml).group(1).strip()
        peopleName = peopleName[peopleName.rfind(' ') + 1:]
        return peopleName

    def __GetAlbumsNameFromHtml(self, rawHtml):
        '''获取相册名字以及地址

        返回元组列表（相册名，地址）
        '''
        albumUrlPattern = re.compile(r'''\n</a>\n<a href="(.*?)\?frommyphoto" class="album-title">.*?<span class="album-name">(.*?)</span>''', re.S)

        albums = []
        for album_url, album_name in albumUrlPattern.findall(rawHtml):
            album_name = album_name.strip()
            if album_name == '<span class="userhead">':
                album_name = u"头像相册"
            elif album_name == '<span class="phone">':
                album_name = u"手机相册"
            elif album_name == '<span class="password">': # 有密码，跳过
                continue
            logger.info("album_url: [%s]  album_name: [%s]" % (album_url, album_name))
            albums.append((album_name, album_url))

        return albums

    def __GetImgUrlsInAlbum(self, album_url):
        album_url += "/bypage/ajax?curPage=0&pagenum=100" # pick 100 pages which has 20 per page
        rawHtml, url = self.requester.Request(album_url)            
        rawHtml = unicode(rawHtml, "utf-8")

        data = json.loads(rawHtml)
        photoList = data['photoList']

        img_urls = []
        for item in photoList:
            img_urls.append((item['title'], item['largeUrl'])) 

        return img_urls

    def __EnsureFolder(self, path):
        if os.path.exists(path) == False:
            os.mkdir(path)        

    def __NormFilename(self, filename):
        filename = re.sub(ur"[\t\r\n\\/:：*?<>|]", "", filename)
        filename = filename.strip(". \n\r")
        return filename

    def __DownloadOneAlbum(self, userid, path):
        download_tasks = self.CreateTaskList(userid, path)
        self.__Download(download_tasks)

    def CreateTaskList(self):
        userid = self.userid
        path = self.path
        path = path.decode('utf-8')
        self.__EnsureFolder(path)
        
        albumsUrl = "http://photo.renren.com/photo/%s/album/relatives" % userid

        # 打开相册首页，以获取每个相册的地址以及名字
        rawHtml, url = self.requester.Request(albumsUrl)            
        rawHtml = unicode(rawHtml, "utf-8")

        # 取得人名
        peopleName = self.__GetPeopleNameFromHtml(rawHtml).strip()
        albums = self.__GetAlbumsNameFromHtml(rawHtml)

        # 更新path
        peopleName = self.__NormFilename(peopleName)
        path = os.path.join(path, peopleName)
        self.__EnsureFolder(path)

        logger.info(peopleName)

        album_img_dict = {}

        # 构造dict[相册名]=img_urls的字典
        for album_name, album_url in albums:
            logger.info("album_name: %s  album_url: %s" % (album_name, album_url))
            
            album_name = self.__NormFilename(album_name)
            album_img_dict[album_name] = self.__GetImgUrlsInAlbum(album_url)

        # 创建文件夹，以及下载任务 
        download_tasks = []
        for album_name, img_urls in album_img_dict.iteritems(): 
            album_path = os.path.join(path, album_name)
            logger.info("Create %s if not exists." % album_path)
            self.__EnsureFolder(album_path)

            index = 1
            name_set = set()
            for alt, img_url in img_urls:
                name = self.__NormFilename(alt)
                if not name:
                    name = str(index)
                    index += 1
                while name in name_set:
                    name += "I"
                name_set.add(name)
                filename = os.path.join(album_path, name + ".jpg")
                download_tasks.append((img_url, filename))

        logger.info("Download Tasks size: %d." % len(download_tasks))

        return download_tasks

    def __Download(self, downloadTasks): 
        taskList = Queue()
        for item in downloadTasks:
            taskList.put(item)

        # 开始并行下载
        threads = []
        for i in xrange(self.threadnum):
            downloader = self.DownloaderThread(taskList)
            downloader.start()
            threads.append(downloader)

        for i, t in enumerate(threads):
            logger.info("Thread %d ended" % i)
            t.join() 

        logger.info("All Thread terminated")



class AllFriendAlbumsDownloader:
    '''下载所有好友的相册
    '''

    class DownloaderThread(threading.Thread):
        def __init__(self, db):
            threading.Thread.__init__(self)
            self.db = db

        def run(self):
            taskList = self.db["TaskList"]
            while len(taskList) > 0:
                try:
                    GlobalShelveMutex.acquire()
                    img_url, filename = taskList.pop() 
                except:
                    logger.error("Exception at Downloader.run()", exc_info=True)
                    continue
                finally:
                    GlobalShelveMutex.release()

                DownloadImage(img_url, filename)

                try:
                    GlobalShelveMutex.acquire()
                    self.db['DoneTask'].add(img_url)
                finally:
                    GlobalShelveMutex.release()


    class TaskListThread(threading.Thread):
        def __init__(self, taskList):
            threading.Thread.__init__(self)
            self.tastList = taskList

        def run(self):
            pass
                

    def Handler(self, requester, path, threadnum=20):
        self.requester = requester
        db = shelve.open(TaskListFilename, writeback = True)
        
        if not db.has_key("TaskList"):
            db["TaskList"] = []
        if not db.has_key("DoneTask"):
            db["DoneTask"] = set()

        logger.info("Task list length: %d" % len(db["TaskList"]))

        if len(db["TaskList"]) == 0: 
            friendsList = RenrenFriendList().Handler(self.requester, None)
            logger.info("Friend List length: %d" % len(friendsList))

            logger.info("Start creating the task list.")
            totalTaskList = []
            for userid, name in friendsList:
                downloader = RenrenAlbumDownloader2012(self.requester, userid, path, threadnum)
                taskList = downloader.CreateTaskList()
                totalTaskList.extend(taskList)
                
            doneSet = db["DoneTask"]
            db["TaskList"] = [item for item in totalTaskList if item not in doneSet]
        else:
            logger.info("There is remain task, resume to download them.")

        threads = []
        for i in xrange(threadnum):
            downloader = self.DownloaderThread(db)
            downloader.start()
            threads.append(downloader)

        for i, t in enumerate(threads):
            logger.info("Thread %d ended" % i)
            t.join() 

        logger.info("All Thread terminated")

        
class SuperRenren:
    '''
    SuperRenren
        用户接口
    '''
    # 创建
    def Create(self, username, password):
        self.requester = RenrenRequester()
        if self.requester.Create(username, password):
            self.__GetInfoFromRequester()
            return True
        return False

    def CreateByCookie(self, cookie):
        self.requester = RenrenRequester()
        if self.requester.CreateByCookie(cookie):
            self.__GetInfoFromRequester()
            return True
        return False

    def __GetInfoFromRequester(self):
        self.userid = self.requester.userid
        self.requestToken = self.requester.requestToken
        self._rtk = self.requester._rtk

    # 发送个人状态
    def PostMsg(self, msg):
        poster = RenrenPostMsg()
        poster.Handle(self.requester, (self.requestToken, self.userid, self._rtk, msg))

    # 发送小组状态        
    def PostGroupMsg(self, groupId, msg):
        poster = RenrenPostGroupMsg()
        poster.Handle(self.requester, (self.requestToken, groupId, msg))

    def GetFriendList(self): 
        friendsList = RenrenFriendList().Handler(self.requester, None)
        return friendsList

    # 下载相册
    def DownloadAlbum(self, userId, path = 'albums', threadnum=20):       
        downloader = RenrenAlbumDownloader2012(self.requester, userId, path, threadnum)
        downloader.Handler()

    # 自动下载所有好友相册
    def DownloadAllFriendsAlbums(self, path = 'albums', threadnumber = 50):
        downloader = AllFriendAlbumsDownloader()
        downloader.Handler(self.requester, path, threadnumber)
