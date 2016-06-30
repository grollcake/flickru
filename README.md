# flickru

플리커에 내 사진들 업로드를 한방에~!


## 사용방법

특정 디렉토리 내의 모든 사진 업로드 (하위 폴더 포함)

    python3 flickru.py -k <api_key> -s <secret_key> -d /path/from

사진 업로드 후 특정 앨범에 사진 포함 (앨범이 없으면 생성 함)

    python3 flickru.py -k <api_key> -s <secret_key> -d /path/from --album "Auto Uploads"

사진 업로드 및 앨범(예, Auto Uploads)에 사진 포함 (앨범이 없으면 생성 함)

    python3 flickru.py -k <api_key> -s <secret_key> -d /path/from -a "Auto Uploads"

사진 업로드 후 로컬 디렉토리의 사진은 삭제

    python3 flickru.py -k <api_key> -s <secret_key> -d /path/from --remove_photo

프로그램 종료하지 않고 계속 실행 (daemon mode)

    python3 flickru.py -k <api_key> -s <secret_key> -d /path/from --remove_photo --daemon


## 기타 옵션

* -t (--tag) 태그 지정
* -i (--title) 제목 지정
* -e (--description) 설명 추가 


## 플리커 인증

* 본인이 사용 할 [API KEY](https://www.flickr.com/services/api/keys/) 생성 필요 
* 사진 업로드를 write 권한이 필요하며 Flickr OAuth 인증으로 토큰 획득 (최초 실행 시 1회만 수행)


## 환경 파일

최초 실행 시 동일 폴더에 `flickru.ini`로 자동 생성.

```
[flickru]
api_key = <your api key>
secret_key = <your secret key>
directory = /path/flickr_uploads
```


## 파일들
* flickru.py   : 업로드 프로그램 
* flickru.ini  : 환경설정 파일 (실행 시 생성)
* flickru.db   : 업로드 이력 관리용 sqlite db (실행 시 생성)
* flickru.log  : 프로그램 실행 로그 (실행 시 생성)
* ~/.flickr/oauth-tokens.sqlite  : 플리커 인증 토큰 보관용 sqlite db (실행 시 생성)


## 필요 사항

* python3
* sqlalchemy
* flickrapi
* urllib3 (1.16 이상) 

필요 모듈 한방에 설치: `pip install --upgrade sqlalchemy flickrapi urllib3`


## 제약 사항

* 파이썬3만 지원
* flickr api 회수 제한으로 일괄 업로드 중 오류 발생할 수 있음 (30분 정도 후에 재시도)
