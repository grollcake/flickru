#!/usr/bin/env python3

""" 플리커에 사진 일괄 업로드!"""
import datetime
import hashlib
import os
import sys
import time
import codecs
import argparse
import configparser
import logging
import logging.handlers
# from xml.etree import ElementTree

import flickrapi
import sqlalchemy
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

APPNAME = 'flickru'
CONFIG_FILE = os.path.join(os.path.dirname(sys.argv[0]), APPNAME + '.ini')
SQLITE_FILE = os.path.join(os.path.dirname(sys.argv[0]), APPNAME + '.db')
LOCK_FILE = os.path.join(os.path.dirname(sys.argv[0]), APPNAME + '.lock')

LOGGER = None
LOGFILE = os.path.join(os.path.dirname(sys.argv[0]), APPNAME + '.log')
LOGLEVEL = logging.DEBUG

OPT = None
FLICKR = None
Base = declarative_base()
session = None

SLEEP_TIME = 60 * 5
DRIP_TIME = 60 * 1
UPLOAD_EXT = ['jpg', 'jpeg', 'png', 'gif', 'avi', 'mov', 'mpg', 'mp4', '3gp']
EXCLUDE_SUBDIR = ['@eaDir', '#recycle', '_ExcludeSync', 'Originals']


class UploadHistory(Base):
    __tablename__ = 'upload_history'
    localpath = sqlalchemy.Column(sqlalchemy.Text, unique=False)
    photo_id = sqlalchemy.Column(sqlalchemy.BIGINT, primary_key=True)
    url = sqlalchemy.Column(sqlalchemy.Text, unique=False)
    date_uploaded = sqlalchemy.Column(sqlalchemy.DateTime, unique=False)
    md5 = sqlalchemy.Column(sqlalchemy.Text, unique=False)

    def __repr__(self):
        return '<UploadHistory: {}({}) is uploaded at {:%Y/%m/%d %H:%M:%S}>'.format(
            self.localpath, self.photo_id, self.date_uploaded)


def _init_console_encoding():
    # utf-8, cp949, euc-kr등으로 자동감지하는 경우에는 그대로 사용하고, 그 외에는 utf-8로 통일!
    encoding = sys.stdout.encoding
    if encoding.replace('-', '').lower() not in ['utf8', 'cp949', 'euckr']:
        sys.stdout = codecs.getwriter('utf-8')(sys.stdout.detach())
        sys.stderr = codecs.getwriter('utf-8')(sys.stderr.detach())
        print('Warn! Current console encoding {} is not supported. Now, using UTF-8 encoding.'.format(encoding))


def _init_args():
    global OPT

    # 사용자 환경 설정 파일이 있으면 읽어들여서 기본값으로 세팅한다.
    defaults = {}
    if os.path.exists(CONFIG_FILE):
        config = configparser.ConfigParser()
        try:
            config.read(CONFIG_FILE)
            defaults = dict(config.items(APPNAME))
        except configparser.NoSectionError as ex:
            LOGGER.warn('환경설정 파일({})에서 [{}] 세션을 읽을 수가 없습니다: {}'.format(APPNAME, CONFIG_FILE, ex))
            LOGGER.warn('환경설정 파일은 무시하고 진행합니다.')
        except configparser.ParsingError as ex:
            LOGGER.error('환경설정 파일({}) 구문 오류입니다: {}'.format(CONFIG_FILE, ex))
            sys.exit(2)

    parser = argparse.ArgumentParser(description='플리커에 다수의 사진을 한방에 업로드!',
                                     formatter_class=argparse.RawTextHelpFormatter)
    parser.add_argument('-k', '--api_key', action='store', metavar='<xxxxxxx>', help='flickr api key', default='')
    parser.add_argument('-s', '--secret_key', action='store', metavar='<sssssss>', help='flickr secret key', default='')
    parser.add_argument('-d', '--directory', action='store', metavar='path', default='.', help='업로드 디렉토리')
    parser.add_argument('-a', '--album', action='store', metavar='<앨범명>', help='업로드한 사진을 앨범에 포함', default='')
    parser.add_argument('-t', '--tag', action='store', metavar='<태그>', help='사진 태그', default='UploadedByFlickru')
    parser.add_argument('-i', '--title', action='store', metavar='<제목>', help='사진 제목', default='')
    parser.add_argument('-e', '--description', action='store', metavar='<주석>', help='사진 주석', default='')
    parser.add_argument('-r', '--remove_photo', action='store_true', help='업로드 후 사진 삭제')
    parser.add_argument('-D', '--daemon', action='store_true', help='종료하지 않고 계속 실행')

    parser.set_defaults(**defaults)
    OPT = parser.parse_args()
    LOGGER.debug(OPT)

    # 환경 파일이 없으면 생성하고 필수 옵션만 기록해둔다.
    if not os.path.exists(CONFIG_FILE):
        LOGGER.debug('환경파일을 생성합니다: {}'.format(os.path.abspath(CONFIG_FILE)))
        with open(CONFIG_FILE, 'w') as configfile:
            configfile.write('[{}]\n'.format(APPNAME) +
                             'api_key = {}\n'.format(OPT.api_key) +
                             'secret_key = {}\n'.format(OPT.secret_key) +
                             'directory = {}\n'.format(OPT.directory))

    if not OPT.api_key or not OPT.secret_key:
        LOGGER.error('api_key, secret_key는 필수 입력입니다.')
        LOGGER.error('사용법을 확인하시려면 -h 옵션을 이용하세요.')
        sys.exit(1)

    return 0


def _init_logging():
    global LOGGER

    # 로깅 모듈 초기화
    LOGGER = logging.getLogger(APPNAME)
    datefmt = '%Y-%m-%d %H:%M:%S'
    stream_fmt = '%(message)s'
    stream_handler = logging.StreamHandler()
    stream_handler.setFormatter(logging.Formatter(stream_fmt, datefmt))
    stream_handler.setLevel(logging.INFO)
    file_fmt = '[%(levelname)s] [%(filename)s:%(lineno)d] %(asctime)s.%(msecs).03d> %(message)s'
    file_handler = logging.handlers.RotatingFileHandler(LOGFILE, maxBytes=10 * 1024 * 1024, backupCount=0,
                                                        encoding='utf-8')
    file_handler.setFormatter(logging.Formatter(file_fmt, datefmt))
    file_handler.setLevel(LOGLEVEL)
    LOGGER.addHandler(stream_handler)
    LOGGER.addHandler(file_handler)
    LOGGER.setLevel(logging.DEBUG)

    return 0


def _init_db():
    global session

    # 데이터베이스 초기화
    LOGGER.debug('sqlite file is {}'.format(os.path.abspath(SQLITE_FILE)))
    engine = sqlalchemy.create_engine('sqlite:///' + SQLITE_FILE)
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)()

    return 0


def _init_flickr_auth():
    global FLICKR

    FLICKR = flickrapi.FlickrAPI(OPT.api_key, OPT.secret_key, store_token=True, format='etree')
    if not FLICKR.token_valid(perms='write'):
        # Get new OAuth credentials
        FLICKR.get_request_token(oauth_callback='oob')
        url = FLICKR.auth_url(perms='write')
        LOGGER.info('\n최초 실행 시 플리커 인증이 필요합니다. 다음 주소를 브라우저에 넣고 플리커 인증을 수행해주세요:')
        LOGGER.info(url)
        token = input('인증 완료 후 생성된 코드를 이곳에 입력해주세요: ')
        FLICKR.get_access_token(token)
        LOGGER.info('인증이 정상적으로 완료되었습니다.\n')

    # OAuth 인증 완료 후 토큰에 저장되어 있는 사용자 정보를 읽어보자
    OPT.user_id = FLICKR.token_cache.token.user_nsid
    OPT.username = FLICKR.token_cache.token.username
    OPT.fullname = FLICKR.token_cache.token.fullname
    LOGGER.info('** [{}]님의 플리커 인증 OK'.format(OPT.username))
    return 0


def md5_checksum(filespec):
    return hashlib.md5(open(filespec, 'rb').read()).hexdigest()


def grab_new_photos(path):
    photos = []
    for root, dirs, files in os.walk(path, topdown=True):
        dirs[:] = [d for d in dirs if d not in EXCLUDE_SUBDIR]  # 세련된 방법의 제외폴더 지정
        for file in files:
            if file.split('.')[-1].lower() in UPLOAD_EXT:
                fullpath = os.path.join(root, file)
                md5 = md5_checksum(fullpath)
                history = session.query(UploadHistory).filter(UploadHistory.md5 == md5).first() 
                if not history:
                    photos.append({'path': fullpath, 'md5': md5})
                elif OPT.remove_photo:
                    os.remove(fullpath)
                    LOGGER.info('<{}>는 이미 업로드한 사진이라 삭제합니다. 사진번호: {}'.format(fullpath, history.photo_id))

    return photos


def insert_history(photo, photo_id):
    url = 'https://www.flickr.com/photos/{}/{}'.format(OPT.user_id, photo_id)
    session.add(UploadHistory(localpath=photo['path'], photo_id=photo_id, url=url,
                              date_uploaded=datetime.datetime.now(), md5=photo['md5']))
    session.commit()


def file_is_in_changing(file):
    md5 = md5_checksum(file)
    time.sleep(1)
    return md5 != md5_checksum(file)


def add_to_album(album_name, photo_id):
    if 'album_id' in OPT:
        rsp = FLICKR.photosets.addPhoto(api_key=OPT.api_key, photoset_id=OPT.album_id, photo_id=photo_id)
    else:
        rsp = FLICKR.photosets.getList(user_id=OPT.user_id)
        # ElementTree.dump(rsp)
        for album in rsp.find('photosets').findall('photoset'):
            if album.findtext('title') == album_name:
                OPT.album_id = album.attrib['id']
                break
        if 'album_id' in OPT:
            rsp = FLICKR.photosets.addPhoto(api_key=OPT.api_key, photoset_id=OPT.album_id, photo_id=photo_id)
        else:
            rsp = FLICKR.photosets.create(api_key=OPT.api_key, title=album_name, primary_photo_id=photo_id)
            OPT.album_id = rsp.find('photoset').attrib['id']


def upload_photo(photos, title, tag, description, remove_photo):
    for idx, photo in enumerate(photos):
        # 변경 중인 파일은 업로드하지 않는다. (예, 복사 중)
        if file_is_in_changing(photo['path']):
            LOGGER.info('({}/{}) <{}>는 현재 변경 중이라서 업로드하지 않습니다.'.format(idx+1, len(photos), photo['path']))
            continue

        dsc = description if description else os.path.basename(photo['path'])
        ttl = title if title else os.path.splitext(os.path.basename(photo['path']))[0]
        LOGGER.debug('FLICKR.upload(filename={}, title={}, tags={}, description={})'.format(photo['path'], ttl, tag,
                                                                                            dsc))
        rsp = FLICKR.upload(filename=photo['path'], title=ttl, tags=tag, description=dsc, is_public='0')
        photo_id = rsp.findtext('photoid')

        if OPT.album:
            add_to_album(OPT.album, photo_id)

        msg = '업로드 완료'
        if remove_photo:
            os.remove(photo['path'])
            msg = '업로드 및 삭제 완료'

        LOGGER.info('({}/{}) <{}> {}. 플리커 사진번호: {}'.format(idx+1, len(photos), photo['path'], msg, photo_id))

        insert_history(photo, photo_id)

        (idx+1) % 10 == 0 and time.sleep(DRIP_TIME)  # 10장 연속 업로드했으면 잠깐 쉬어야지..

    return len(photos)


def main():
    _init_console_encoding()
    _init_logging()
    _init_args()
    _init_db()
    _init_flickr_auth()

    uploaded = 0
    try:
        while True:
            photos = grab_new_photos(OPT.directory)
            if photos:
                uploaded += upload_photo(photos, OPT.title, OPT.tag, OPT.description, OPT.remove_photo)
            if not OPT.daemon:
                break
            LOGGER.debug('마지막 확인시간: {}'.format(str(datetime.datetime.now())))
            time.sleep(SLEEP_TIME)

    except KeyboardInterrupt:
        pass

    LOGGER.info('** 총 {}개의 사진을 업로드 했습니다!'.format(uploaded))

    return 0


if __name__ == '__main__':
    sys.exit(main())
