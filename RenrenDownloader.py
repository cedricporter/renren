#!/usr/bin/env python
# -*- coding: utf-8 -*-  
# author:  Hua Liang [ Stupid ET ]
# email:   et@everet.org
# website: http://EverET.org
#


from Renren import SuperRenren
import time, os

def main():
    dl, dg = {}, {}
    execfile('user.txt', dg, dl)
    try:
        username = dl['username']
        password = dl['password']
        cookie = dl['cookie']
    except:
        pass

    renren = SuperRenren()
    if renren.Create(username, password) or renren.CreateByCookie(cookie):
        # renren.PostMsg(time.asctime())
        # renren.PostGroupMsg('387635422', '%s' % time.asctime())
        # renren.DownloadAlbum('333982368', 'sss') 
        # renren.DownloadAlbum('285201751', 'cai')
        # renren.DownloadAlbum('305263375', 'cai') 
        renren.DownloadAllFriendsAlbums(threadnumber=100)
    
if __name__ == '__main__':
    main()
    
