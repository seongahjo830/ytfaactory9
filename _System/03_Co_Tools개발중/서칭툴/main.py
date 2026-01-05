import streamlit as st
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import pandas as pd
from datetime import datetime, timedelta
import re
import os
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api._errors import TranscriptsDisabled, NoTranscriptFound

# 페이지 설정
st.set_page_config(
    page_title="유튜브 황금 주제 발굴기",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# KeyKey1.txt에서 YouTube API 키 자동 로드
def load_youtube_api_key():
    """KeyKey1.txt 파일에서 YouTube API 키를 자동으로 읽어옵니다."""
    try:
        key_file_path = os.path.join(os.path.dirname(__file__), 'KeyKey1.txt')
        if os.path.exists(key_file_path):
            with open(key_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # YouTube API 키 패턴 찾기
            patterns = [
                r'유튜브\s*api\s*검색키[^:]*:\s*([A-Za-z0-9_-]+)',
                r'유튜브\s*사용자인증키[^:]*:\s*([A-Za-z0-9_-]+)',
                r'유튜브[^:]*키[^:]*:\s*([A-Za-z0-9_-]+)',
            ]
            
            for pattern in patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    # AIzaSy로 시작하는 키만 반환 (YouTube API 키 형식)
                    for match in matches:
                        if match.startswith('AIzaSy') and len(match) > 30:
                            return match.strip()
            
            # 패턴으로 못 찾으면 직접 검색
            lines = content.split('\n')
            for line in lines:
                if '유튜브' in line.lower() and 'AIzaSy' in line:
                    # AIzaSy로 시작하는 키 추출
                    key_match = re.search(r'AIzaSy[A-Za-z0-9_-]+', line)
                    if key_match:
                        return key_match.group()
        
        # 기본값 (KeyKey1.txt에서 찾지 못한 경우)
        return "AIzaSyBG1FScYQ6A8WBRV7VadtvrnPDjjmgiG5o"
    except Exception as e:
        # 오류 발생 시 기본값 반환
        return "AIzaSyBG1FScYQ6A8WBRV7VadtvrnPDjjmgiG5o"

# 기본 API 키 로드
DEFAULT_API_KEY = load_youtube_api_key()

# 사이드바 설정
with st.sidebar:
    st.title("⚙️ 설정")
    st.markdown("---")
    
    # API 키 입력 (자동으로 KeyKey1.txt에서 로드된 키가 기본값으로 설정됨)
    api_key = st.text_input(
        "YouTube API 키 입력",
        value=DEFAULT_API_KEY,
        type="password",
        help="Google Cloud Console에서 발급받은 YouTube Data API v3 키를 입력하세요. (KeyKey1.txt에서 자동 로드됨)"
    )
    
    st.markdown("---")
    
    # 모드 선택
    st.subheader("🎯 모드 선택")
    mode = st.radio(
        "사용 모드",
        ["🔍 키워드 검색", "🔥 트렌딩 주제 찾기"],
        index=0
    )
    
    st.markdown("---")
    
    if mode == "🔍 키워드 검색":
        # 키워드 검색
        st.subheader("🔍 검색")
        test_keyword = st.text_input(
            "검색 키워드",
            placeholder="예: 파이썬 튜토리얼",
            help="유튜브에서 검색할 키워드를 입력하세요."
        )
        
        max_results = st.slider(
            "최대 결과 수",
            min_value=5,
            max_value=50,
            value=10,
            step=5
        )
        
        search_button = st.button("🔎 검색 실행", type="primary")
        trending_button = False
    else:
        # 트렌딩 주제 찾기
        st.subheader("🔥 트렌딩 주제")
        
        trending_type = st.selectbox(
            "트렌딩 타입",
            ["📈 급증 주제", "🎯 카테고리별 인기", "💡 키워드 추천"],
            index=0
        )
        
        if trending_type == "🎯 카테고리별 인기":
            category_options = {
                "전체": None,
                "음악": "10",
                "게임": "20",
                "자동차": "2",
                "뉴스": "25",
                "스포츠": "17",
                "여행": "19",
                "교육": "27",
                "과학기술": "28",
                "엔터테인먼트": "24"
            }
            selected_category = st.selectbox("카테고리 선택", list(category_options.keys()))
            category_id = category_options[selected_category]
        else:
            category_id = None
        
        max_results = st.slider(
            "최대 결과 수",
            min_value=10,
            max_value=50,
            value=20,
            step=5
        )
        
        trending_button = st.button("🔥 트렌딩 찾기", type="primary")
        search_button = False
        test_keyword = ""
    
    st.markdown("---")
    
    # 랭킹 선택
    st.subheader("📊 랭킹 선택")
    ranking_options = [
        '최종 마스터 추천',
        '조회수 효율',
        '급등 에너지',
        '블루오션 지수',
        '글로벌 트렌드 전이',
        '콘텐츠 노후도',
        '참여 밀도',
        '롱테일 확장성',
        '폭발 성장형 (칵테일 A)',
        '저리스크 침투형 (칵테일 B)',
        '팬덤 형성형 (칵테일 C)'
    ]
    
    selected_ranking = st.selectbox(
        "랭킹 타입 선택",
        ranking_options,
        index=0
    )
    
    st.markdown("---")
    
    # 가중치 조절 (최종 마스터 추천용)
    st.subheader("⚖️ 가중치 조절")
    st.caption("최종 마스터 추천 점수 계산 시 사용됩니다.")
    
    # 가중치 초기화 (세션 상태에 없으면 기본값 사용)
    if 'weights' not in st.session_state:
        st.session_state['weights'] = {
            'view_efficiency': 1.0,
            'trending_energy': 1.0,
            'blue_ocean': 1.0,
            'global_trend': 1.0,
            'content_aging': 1.0,
            'engagement_density': 1.0,
            'longtail': 1.0
        }
    
    # 가중치 슬라이더
    weights = {
        'view_efficiency': st.slider(
            "조회수 효율", 0.0, 2.0, 
            st.session_state['weights']['view_efficiency'], 0.1,
            key='weight_view_efficiency'
        ),
        'trending_energy': st.slider(
            "급등 에너지", 0.0, 2.0, 
            st.session_state['weights']['trending_energy'], 0.1,
            key='weight_trending_energy'
        ),
        'blue_ocean': st.slider(
            "블루오션 지수", 0.0, 2.0, 
            st.session_state['weights']['blue_ocean'], 0.1,
            key='weight_blue_ocean'
        ),
        'global_trend': st.slider(
            "글로벌 트렌드", 0.0, 2.0, 
            st.session_state['weights']['global_trend'], 0.1,
            key='weight_global_trend'
        ),
        'content_aging': st.slider(
            "콘텐츠 노후도", 0.0, 2.0, 
            st.session_state['weights']['content_aging'], 0.1,
            key='weight_content_aging'
        ),
        'engagement_density': st.slider(
            "참여 밀도", 0.0, 2.0, 
            st.session_state['weights']['engagement_density'], 0.1,
            key='weight_engagement_density'
        ),
        'longtail': st.slider(
            "롱테일 확장성", 0.0, 2.0, 
            st.session_state['weights']['longtail'], 0.1,
            key='weight_longtail'
        )
    }
    
    # 가중치 합계 표시
    weight_sum = sum(weights.values())
    if weight_sum == 0:
        st.warning("⚠️ 가중치 합이 0입니다. 최소 하나의 지표는 0보다 커야 합니다.")
    else:
        st.caption(f"가중치 합계: {weight_sum:.1f}")
    
    # 가중치 변경 감지 및 저장
    prev_weights = st.session_state.get('weights', {})
    if prev_weights and weights != prev_weights:
        st.session_state['weights_changed'] = True
    else:
        st.session_state['weights_changed'] = False
    
    # 현재 가중치 저장
    st.session_state['weights'] = weights

# 메인 화면
st.title("🚀 유튜브 황금 주제 발굴기")
st.markdown("**데이터 기반 주제 발굴 대시보드**")
st.markdown("---")

# 트렌딩 영상 가져오기 함수
@st.cache_data(show_spinner=False, ttl=3600)  # 1시간 캐싱
def get_trending_videos(api_key, region_code='KR', category_id=None, max_results=50):
    """YouTube 트렌딩 영상 가져오기"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 트렌딩 영상 요청
        request_params = {
            'part': 'snippet,statistics,contentDetails',
            'chart': 'mostPopular',
            'regionCode': region_code,
            'maxResults': min(max_results, 50)
        }
        
        if category_id:
            request_params['videoCategoryId'] = category_id
        
        videos_response = youtube.videos().list(**request_params).execute()
        
        results = []
        video_ids = [item['id'] for item in videos_response.get('items', [])]
        channel_ids = list(set([item['snippet']['channelId'] for item in videos_response.get('items', [])]))
        
        # 채널 정보 가져오기
        channel_info = {}
        if channel_ids:
            for i in range(0, len(channel_ids), 50):
                batch = channel_ids[i:i+50]
                channels_response = youtube.channels().list(
                    part='statistics,snippet',
                    id=','.join(batch)
                ).execute()
                
                for channel in channels_response.get('items', []):
                    channel_info[channel['id']] = {
                        'subscriber_count': int(channel['statistics'].get('subscriberCount', 0)),
                        'video_count': int(channel['statistics'].get('videoCount', 0)),
                        'view_count': int(channel['statistics'].get('viewCount', 0))
                    }
        
        for video in videos_response.get('items', []):
            channel_id = video['snippet']['channelId']
            channel_data = channel_info.get(channel_id, {
                'subscriber_count': 0,
                'video_count': 0,
                'view_count': 0
            })
            
            # 영상 나이 계산
            published_date = datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00'))
            days_old = (datetime.now(published_date.tzinfo) - published_date).days
            
            video_data = {
                'video_id': video['id'],
                'title': video['snippet']['title'],
                'channel_id': channel_id,
                'channel_title': video['snippet']['channelTitle'],
                'published_at': video['snippet']['publishedAt'],
                'days_old': days_old,
                'view_count': int(video['statistics'].get('viewCount', 0)),
                'like_count': int(video['statistics'].get('likeCount', 0)),
                'comment_count': int(video['statistics'].get('commentCount', 0)),
                'subscriber_count': channel_data['subscriber_count'],
                'channel_video_count': channel_data['video_count'],
                'thumbnail': video['snippet']['thumbnails']['high']['url'],
                'description': video['snippet']['description'][:200] + '...' if len(video['snippet']['description']) > 200 else video['snippet']['description'],
                'url': f"https://www.youtube.com/watch?v={video['id']}"
            }
            results.append(video_data)
        
        return results, None
        
    except HttpError as e:
        error_msg = f"API 오류 발생: {e.resp.status} - {e.content.decode('utf-8')}"
        return None, error_msg
    except Exception as e:
        error_msg = f"오류 발생: {str(e)}"
        return None, error_msg


# 급증 키워드 분석 함수
@st.cache_data(show_spinner=False, ttl=1800)  # 30분 캐싱
def analyze_trending_keywords(api_key, days=7, max_results=50):
    """급증 키워드 분석 - 최근 업로드된 영상 중 조회수 급증 영상 찾기"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 최근 업로드된 영상 검색 (조회수 순)
        search_response = youtube.search().list(
            part='id,snippet',
            type='video',
            order='viewCount',
            publishedAfter=(datetime.now() - timedelta(days=days)).isoformat() + 'Z',
            regionCode='KR',
            maxResults=min(max_results, 50)
        ).execute()
        
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        
        if not video_ids:
            return [], None
        
        # 영상 상세 정보 가져오기
        videos_response = youtube.videos().list(
            part='statistics,snippet,contentDetails',
            id=','.join(video_ids)
        ).execute()
        
        results = []
        channel_ids = list(set([item['snippet']['channelId'] for item in videos_response.get('items', [])]))
        
        # 채널 정보 가져오기
        channel_info = {}
        if channel_ids:
            for i in range(0, len(channel_ids), 50):
                batch = channel_ids[i:i+50]
                channels_response = youtube.channels().list(
                    part='statistics,snippet',
                    id=','.join(batch)
                ).execute()
                
                for channel in channels_response.get('items', []):
                    channel_info[channel['id']] = {
                        'subscriber_count': int(channel['statistics'].get('subscriberCount', 0)),
                        'video_count': int(channel['statistics'].get('videoCount', 0)),
                        'view_count': int(channel['statistics'].get('viewCount', 0))
                    }
        
        for video in videos_response.get('items', []):
            channel_id = video['snippet']['channelId']
            channel_data = channel_info.get(channel_id, {
                'subscriber_count': 0,
                'video_count': 0,
                'view_count': 0
            })
            
            # 영상 나이 계산
            published_date = datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00'))
            days_old = (datetime.now(published_date.tzinfo) - published_date).days
            
            # 급증 지수 계산 (조회수 / 영상 나이)
            surge_score = video['statistics'].get('viewCount', 0) / max(days_old, 1) if days_old > 0 else 0
            
            video_data = {
                'video_id': video['id'],
                'title': video['snippet']['title'],
                'channel_id': channel_id,
                'channel_title': video['snippet']['channelTitle'],
                'published_at': video['snippet']['publishedAt'],
                'days_old': days_old,
                'view_count': int(video['statistics'].get('viewCount', 0)),
                'like_count': int(video['statistics'].get('likeCount', 0)),
                'comment_count': int(video['statistics'].get('commentCount', 0)),
                'subscriber_count': channel_data['subscriber_count'],
                'channel_video_count': channel_data['video_count'],
                'surge_score': surge_score,  # 급증 지수
                'thumbnail': video['snippet']['thumbnails']['high']['url'],
                'description': video['snippet']['description'][:200] + '...' if len(video['snippet']['description']) > 200 else video['snippet']['description'],
                'url': f"https://www.youtube.com/watch?v={video['id']}"
            }
            results.append(video_data)
        
        # 급증 지수로 정렬
        results.sort(key=lambda x: x['surge_score'], reverse=True)
        
        return results, None
        
    except HttpError as e:
        error_msg = f"API 오류 발생: {e.resp.status} - {e.content.decode('utf-8')}"
        return None, error_msg
    except Exception as e:
        error_msg = f"오류 발생: {str(e)}"
        return None, error_msg


# 키워드 추천 함수
def get_recommended_keywords(api_key, base_keyword, max_results=20):
    """기존 키워드와 관련된 트렌딩 키워드 추천"""
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 기본 키워드로 검색
        search_response = youtube.search().list(
            q=base_keyword,
            part='id,snippet',
            type='video',
            maxResults=min(max_results, 50),
            order='relevance',
            regionCode='KR'
        ).execute()
        
        # 제목에서 키워드 추출
        keywords_freq = {}
        
        for item in search_response.get('items', []):
            title = item['snippet']['title']
            # 제목을 단어로 분리
            words = re.findall(r'\b\w+\b', title.lower())
            
            # 기본 키워드 제외하고 빈도 계산
            base_words = base_keyword.lower().split()
            for word in words:
                if len(word) > 2 and word not in base_words and word not in ['the', 'and', 'for', 'are', 'but', 'not', 'you', 'all', 'can', 'her', 'was', 'one', 'our', 'out', 'day', 'get', 'has', 'him', 'his', 'how', 'its', 'may', 'new', 'now', 'old', 'see', 'two', 'way', 'who', 'boy', 'did', 'its', 'let', 'put', 'say', 'she', 'too', 'use']:
                    keywords_freq[word] = keywords_freq.get(word, 0) + 1
        
        # 빈도순으로 정렬
        sorted_keywords = sorted(keywords_freq.items(), key=lambda x: x[1], reverse=True)
        
        # 상위 키워드 반환
        recommended = [word for word, freq in sorted_keywords[:10] if freq > 1]
        
        return recommended, None
        
    except Exception as e:
        error_msg = f"오류 발생: {str(e)}"
        return None, error_msg


# YouTube API 검색 함수 (개선된 버전)
@st.cache_data(show_spinner=False)
def search_youtube_enhanced(api_key, keyword, max_results=10):
    """
    YouTube Data API v3를 사용하여 키워드로 영상 검색 및 상세 데이터 수집
    
    Args:
        api_key: YouTube Data API v3 키
        keyword: 검색 키워드
        max_results: 최대 결과 수
    
    Returns:
        검색 결과 리스트 (채널 구독자 수 등 추가 정보 포함)
    """
    try:
        youtube = build('youtube', 'v3', developerKey=api_key)
        
        # 검색 요청
        search_response = youtube.search().list(
            q=keyword,
            part='id,snippet',
            type='video',
            maxResults=max_results,
            order='relevance',
            regionCode='KR'
        ).execute()
        
        results = []
        video_ids = [item['id']['videoId'] for item in search_response.get('items', [])]
        channel_ids = list(set([item['snippet']['channelId'] for item in search_response.get('items', [])]))
        
        # 채널 정보 가져오기 (구독자 수 등)
        channel_info = {}
        if channel_ids:
            for i in range(0, len(channel_ids), 50):  # API 제한: 한 번에 최대 50개
                batch = channel_ids[i:i+50]
                channels_response = youtube.channels().list(
                    part='statistics,snippet',
                    id=','.join(batch)
                ).execute()
                
                for channel in channels_response.get('items', []):
                    channel_info[channel['id']] = {
                        'subscriber_count': int(channel['statistics'].get('subscriberCount', 0)),
                        'video_count': int(channel['statistics'].get('videoCount', 0)),
                        'view_count': int(channel['statistics'].get('viewCount', 0))
                    }
        
        if video_ids:
            # 영상 상세 정보 가져오기
            videos_response = youtube.videos().list(
                part='statistics,snippet,contentDetails',
                id=','.join(video_ids)
            ).execute()
            
            # 검색 결과에서 채널 ID 매핑
            video_to_channel = {item['id']['videoId']: item['snippet']['channelId'] 
                              for item in search_response.get('items', [])}
            
            for video in videos_response.get('items', []):
                channel_id = video_to_channel.get(video['id'])
                channel_data = channel_info.get(channel_id, {
                    'subscriber_count': 0,
                    'video_count': 0,
                    'view_count': 0
                })
                
                # 영상 나이 계산
                published_date = datetime.fromisoformat(video['snippet']['publishedAt'].replace('Z', '+00:00'))
                days_old = (datetime.now(published_date.tzinfo) - published_date).days
                
                video_data = {
                    'video_id': video['id'],
                    'title': video['snippet']['title'],
                    'channel_id': channel_id,
                    'channel_title': video['snippet']['channelTitle'],
                    'published_at': video['snippet']['publishedAt'],
                    'days_old': days_old,
                    'view_count': int(video['statistics'].get('viewCount', 0)),
                    'like_count': int(video['statistics'].get('likeCount', 0)),
                    'comment_count': int(video['statistics'].get('commentCount', 0)),
                    'subscriber_count': channel_data['subscriber_count'],
                    'channel_video_count': channel_data['video_count'],
                    'thumbnail': video['snippet']['thumbnails']['high']['url'],
                    'description': video['snippet']['description'][:200] + '...' if len(video['snippet']['description']) > 200 else video['snippet']['description'],
                    'url': f"https://www.youtube.com/watch?v={video['id']}"
                }
                results.append(video_data)
        
        # 검색 결과 수 (블루오션 지수 계산용)
        total_results = search_response.get('pageInfo', {}).get('totalResults', len(results))
        
        return results, total_results, None
        
    except HttpError as e:
        error_msg = f"API 오류 발생: {e.resp.status} - {e.content.decode('utf-8')}"
        return None, None, error_msg
    except Exception as e:
        error_msg = f"오류 발생: {str(e)}"
        return None, None, error_msg


# 숫자를 한국어 형식으로 변환하는 함수
def format_korean_number(num):
    """숫자를 한국어 형식으로 변환 (예: 67000 -> 6만7천)"""
    if num == 0:
        return "0"
    
    num = int(num)
    result = []
    
    # 억 단위
    if num >= 100000000:
        eok = num // 100000000
        result.append(f"{eok}억")
        num = num % 100000000
    
    # 만 단위
    if num >= 10000:
        man = num // 10000
        result.append(f"{man}만")
        num = num % 10000
    
    # 천 단위
    if num >= 1000:
        cheon = num // 1000
        result.append(f"{cheon}천")
        num = num % 1000
    
    # 백 단위
    if num >= 100:
        baek = num // 100
        result.append(f"{baek}백")
        num = num % 100
    
    # 십 단위
    if num >= 10:
        sip = num // 10
        result.append(f"{sip}십")
        num = num % 10
    
    # 일의 자리
    if num > 0:
        result.append(str(num))
    
    return "".join(result) if result else "0"


# 7가지 지표 계산 함수들
def normalize_score(value, min_val, max_val, reverse=False):
    """값을 0~100점으로 정규화"""
    if max_val == min_val or max_val == 0:
        return 50.0  # 기본값
    normalized = ((value - min_val) / (max_val - min_val)) * 100
    if reverse:
        normalized = 100 - normalized
    return max(0, min(100, normalized))


def calculate_view_efficiency(df):
    """1. 조회수 효율: 영상 조회수 / 채널 구독자 수"""
    df['view_efficiency'] = df.apply(
        lambda row: row['view_count'] / max(row['subscriber_count'], 1), 
        axis=1
    )
    df['view_efficiency_score'] = df['view_efficiency'].apply(
        lambda x: normalize_score(x, df['view_efficiency'].min(), df['view_efficiency'].max())
    )
    return df


def calculate_trending_energy(df):
    """2. 급등 에너지: 최근 업로드 + 조회수 성장률 근사"""
    # 영상이 최근일수록, 조회수가 높을수록 급등 에너지 높음
    df['trending_energy'] = df.apply(
        lambda row: (row['view_count'] / max(row['days_old'], 1)) * (1 / max(row['days_old'], 1)),
        axis=1
    )
    df['trending_energy_score'] = df['trending_energy'].apply(
        lambda x: normalize_score(x, df['trending_energy'].min(), df['trending_energy'].max())
    )
    return df


def calculate_blue_ocean_index(df, total_search_results):
    """3. 블루오션 지수: 검색량 / 최근 업로드 영상 수"""
    # 검색 결과 수 / 영상 수 (영상이 적을수록 블루오션)
    recent_videos = len(df[df['days_old'] <= 30])  # 최근 30일 내 영상
    if recent_videos == 0:
        recent_videos = 1
    blue_ocean_ratio = total_search_results / recent_videos
    df['blue_ocean_index'] = blue_ocean_ratio
    # 값이 클수록 블루오션 (정규화는 전체 데이터 기준)
    df['blue_ocean_index_score'] = df['blue_ocean_index'].apply(
        lambda x: normalize_score(x, df['blue_ocean_index'].min(), df['blue_ocean_index'].max())
    )
    return df


def calculate_global_trend_transfer(df):
    """4. 글로벌 트렌드 전이: 해외 데이터 없으므로 영상의 글로벌 성과 근사"""
    # 조회수와 참여도가 높은 영상이 글로벌 트렌드 가능성 높음
    df['global_trend_transfer'] = df['view_count'] * (df['like_count'] + df['comment_count'])
    df['global_trend_transfer_score'] = df['global_trend_transfer'].apply(
        lambda x: normalize_score(x, df['global_trend_transfer'].min(), df['global_trend_transfer'].max())
    )
    return df


def calculate_content_aging(df):
    """5. 콘텐츠 노후도: 상위 노출 영상들의 평균 제작 시기"""
    # 오래된 영상이 많을수록 기회 (days_old가 클수록 점수 높음)
    df['content_aging_score'] = df['days_old'].apply(
        lambda x: normalize_score(x, df['days_old'].min(), df['days_old'].max())
    )
    return df


def calculate_engagement_density(df):
    """6. 참여 밀도: (좋아요 + 댓글) / 조회수"""
    df['engagement_density'] = df.apply(
        lambda row: (row['like_count'] + row['comment_count']) / max(row['view_count'], 1),
        axis=1
    )
    df['engagement_density_score'] = df['engagement_density'].apply(
        lambda x: normalize_score(x, df['engagement_density'].min(), df['engagement_density'].max())
    )
    return df


def calculate_longtail_expandability(df):
    """7. 롱테일 확장성: 관련 키워드 풍부함 근사"""
    # 설명 길이, 제목 길이, 댓글 수 등을 종합하여 근사
    df['longtail_expandability'] = df.apply(
        lambda row: len(str(row['description'])) + len(str(row['title'])) + row['comment_count'],
        axis=1
    )
    df['longtail_expandability_score'] = df['longtail_expandability'].apply(
        lambda x: normalize_score(x, df['longtail_expandability'].min(), df['longtail_expandability'].max())
    )
    return df


def calculate_all_metrics(df, total_search_results):
    """모든 지표 계산"""
    df = calculate_view_efficiency(df.copy())
    df = calculate_trending_energy(df.copy())
    df = calculate_blue_ocean_index(df.copy(), total_search_results)
    df = calculate_global_trend_transfer(df.copy())
    df = calculate_content_aging(df.copy())
    df = calculate_engagement_density(df.copy())
    df = calculate_longtail_expandability(df.copy())
    return df


def calculate_cocktail_metrics(df):
    """3가지 칵테일 지표 계산"""
    # 칵테일 A (폭발 성장형): 급등 에너지 + 글로벌 트렌드
    df['cocktail_a_score'] = (df['trending_energy_score'] + df['global_trend_transfer_score']) / 2
    
    # 칵테일 B (저리스크 침투형): 블루오션 + 콘텐츠 노후도
    df['cocktail_b_score'] = (df['blue_ocean_index_score'] + df['content_aging_score']) / 2
    
    # 칵테일 C (팬덤 형성형): 조회수 효율 + 참여 밀도
    df['cocktail_c_score'] = (df['view_efficiency_score'] + df['engagement_density_score']) / 2
    
    return df


def calculate_master_score(df, weights):
    """최종 마스터 추천 점수 계산 (가중치 적용)"""
    weight_sum = sum(weights.values())
    
    # 가중치 합이 0이면 모든 가중치를 1로 설정
    if weight_sum == 0:
        weight_sum = 7.0  # 모든 가중치를 1로 간주
        df['master_score'] = (
            df['view_efficiency_score'] +
            df['trending_energy_score'] +
            df['blue_ocean_index_score'] +
            df['global_trend_transfer_score'] +
            df['content_aging_score'] +
            df['engagement_density_score'] +
            df['longtail_expandability_score']
        ) / 7.0
    else:
        df['master_score'] = (
            weights['view_efficiency'] * df['view_efficiency_score'] +
            weights['trending_energy'] * df['trending_energy_score'] +
            weights['blue_ocean'] * df['blue_ocean_index_score'] +
            weights['global_trend'] * df['global_trend_transfer_score'] +
            weights['content_aging'] * df['content_aging_score'] +
            weights['engagement_density'] * df['engagement_density_score'] +
            weights['longtail'] * df['longtail_expandability_score']
        ) / weight_sum
    
    return df


def get_ranking_data(df, ranking_type):
    """랭킹 타입에 따라 정렬된 데이터 반환"""
    ranking_map = {
        '조회수 효율': 'view_efficiency_score',
        '급등 에너지': 'trending_energy_score',
        '블루오션 지수': 'blue_ocean_index_score',
        '글로벌 트렌드 전이': 'global_trend_transfer_score',
        '콘텐츠 노후도': 'content_aging_score',
        '참여 밀도': 'engagement_density_score',
        '롱테일 확장성': 'longtail_expandability_score',
        '폭발 성장형 (칵테일 A)': 'cocktail_a_score',
        '저리스크 침투형 (칵테일 B)': 'cocktail_b_score',
        '팬덤 형성형 (칵테일 C)': 'cocktail_c_score',
        '최종 마스터 추천': 'master_score'
    }
    
    if ranking_type not in ranking_map:
        return df.sort_values('master_score', ascending=False)
    
    score_column = ranking_map[ranking_type]
    return df.sort_values(score_column, ascending=False).reset_index(drop=True)


def get_recommendation_reason(row, ranking_type):
    """추천 이유 텍스트 생성"""
    reasons = []
    
    if ranking_type == '조회수 효율':
        reasons.append(f"조회수 효율 {row['view_efficiency_score']:.1f}점")
        reasons.append(f"작은 채널({row['subscriber_count']:,}명)이 높은 조회수({row['view_count']:,}) 달성")
    elif ranking_type == '급등 에너지':
        reasons.append(f"급등 에너지 {row['trending_energy_score']:.1f}점")
        reasons.append(f"최근 {row['days_old']}일 전 업로드, 빠른 성장세")
    elif ranking_type == '블루오션 지수':
        reasons.append(f"블루오션 지수 {row['blue_ocean_index_score']:.1f}점")
        reasons.append("수요 대비 공급이 적은 주제")
    elif ranking_type == '글로벌 트렌드 전이':
        reasons.append(f"글로벌 트렌드 {row['global_trend_transfer_score']:.1f}점")
        reasons.append(f"높은 조회수와 참여도({row['like_count']:,} 좋아요, {row['comment_count']:,} 댓글)")
    elif ranking_type == '콘텐츠 노후도':
        reasons.append(f"콘텐츠 노후도 {row['content_aging_score']:.1f}점")
        reasons.append(f"{row['days_old']}일 전 업로드, 새로운 콘텐츠 기회")
    elif ranking_type == '참여 밀도':
        reasons.append(f"참여 밀도 {row['engagement_density_score']:.1f}점")
        reasons.append(f"시청자 반응이 뜨거움 ({(row['like_count'] + row['comment_count']) / max(row['view_count'], 1) * 100:.2f}%)")
    elif ranking_type == '롱테일 확장성':
        reasons.append(f"롱테일 확장성 {row['longtail_expandability_score']:.1f}점")
        reasons.append("관련 키워드 및 연관 검색어 확장 가능성 높음")
    elif ranking_type == '폭발 성장형 (칵테일 A)':
        reasons.append(f"폭발 성장형 점수 {row['cocktail_a_score']:.1f}점")
        reasons.append(f"급등 에너지({row['trending_energy_score']:.1f}) + 글로벌 트렌드({row['global_trend_transfer_score']:.1f})")
    elif ranking_type == '저리스크 침투형 (칵테일 B)':
        reasons.append(f"저리스크 침투형 점수 {row['cocktail_b_score']:.1f}점")
        reasons.append(f"블루오션({row['blue_ocean_index_score']:.1f}) + 콘텐츠 노후도({row['content_aging_score']:.1f})")
    elif ranking_type == '팬덤 형성형 (칵테일 C)':
        reasons.append(f"팬덤 형성형 점수 {row['cocktail_c_score']:.1f}점")
        reasons.append(f"조회수 효율({row['view_efficiency_score']:.1f}) + 참여 밀도({row['engagement_density_score']:.1f})")
    elif ranking_type == '최종 마스터 추천':
        reasons.append(f"종합 점수 {row['master_score']:.1f}점")
        top_metrics = []
        if row['view_efficiency_score'] > 70:
            top_metrics.append(f"조회수 효율 {row['view_efficiency_score']:.1f}")
        if row['trending_energy_score'] > 70:
            top_metrics.append(f"급등 에너지 {row['trending_energy_score']:.1f}")
        if row['engagement_density_score'] > 70:
            top_metrics.append(f"참여 밀도 {row['engagement_density_score']:.1f}")
        if top_metrics:
            reasons.append("우수 지표: " + ", ".join(top_metrics))
    
    return " | ".join(reasons)


@st.cache_data(show_spinner=False)
def get_video_transcript(video_id):
    """YouTube 영상의 자막(스크립트)을 가져옵니다."""
    try:
        # 한국어 자막 우선 시도
        transcript_list = YouTubeTranscriptApi.list_transcripts(video_id)
        
        # 한국어 자막 찾기
        try:
            transcript = transcript_list.find_transcript(['ko', 'ko-KR'])
            transcript_data = transcript.fetch()
        except:
            # 한국어가 없으면 자동 생성 자막 시도
            try:
                transcript = transcript_list.find_generated_transcript(['ko', 'ko-KR'])
                transcript_data = transcript.fetch()
            except:
                # 영어 자막 시도
                try:
                    transcript = transcript_list.find_transcript(['en', 'en-US'])
                    transcript_data = transcript.fetch()
                except:
                    # 첫 번째 사용 가능한 자막 사용
                    transcript = transcript_list.find_manually_created_transcript(['ko', 'en'])
                    transcript_data = transcript.fetch()
        
        # 자막 텍스트만 추출
        script_text = ' '.join([item['text'] for item in transcript_data])
        return script_text, None
    except TranscriptsDisabled:
        return None, "이 영상은 자막이 비활성화되어 있습니다."
    except NoTranscriptFound:
        return None, "이 영상에는 사용 가능한 자막이 없습니다."
    except Exception as e:
        return None, f"자막을 가져오는 중 오류가 발생했습니다: {str(e)}"


def generate_video_script(row, rank, ranking_type, transcript_text=None):
    """영상 정보와 자막을 포함한 스크립트 생성"""
    subscriber_korean = format_korean_number(row['subscriber_count'])
    view_korean = format_korean_number(row['view_count'])
    like_korean = format_korean_number(row['like_count'])
    comment_korean = format_korean_number(row['comment_count'])
    
    # 업로드 일수
    days_old = int(row['days_old'])
    if days_old == 0:
        upload_text = "오늘 업로드"
    elif days_old == 1:
        upload_text = "1일 전"
    elif days_old < 30:
        upload_text = f"{days_old}일 전"
    elif days_old < 365:
        months = days_old // 30
        upload_text = f"{months}개월 전"
    else:
        years = days_old // 365
        upload_text = f"{years}년 전"
    
    script = f"""🎬 영상 정보

📌 제목: {row['title']}
📺 채널: {row['channel_title']} (구독자 {subscriber_korean}명)
🔗 URL: {row['url']}

📊 통계:
• 조회수: {view_korean}회
• 좋아요: {like_korean}개
• 댓글: {comment_korean}개
• 업로드: {upload_text}

🏆 랭킹: {ranking_type} {rank}위
💡 추천 이유: {get_recommendation_reason(row, ranking_type)}
"""
    
    # 자막이 있으면 추가
    if transcript_text:
        script += f"""

📝 영상 자막 (스크립트):

{transcript_text}
"""
    else:
        script += "\n\n⚠️ 이 영상에는 자막이 없거나 가져올 수 없습니다."
    
    return script

# 트렌딩 주제 찾기
if trending_button:
    if not api_key:
        st.error("❌ API 키를 입력해주세요.")
    else:
        if trending_type == "📈 급증 주제":
            with st.spinner("📈 급증 주제 분석 중..."):
                results, error = analyze_trending_keywords(api_key, days=7, max_results=max_results)
            
            if error:
                st.error(f"❌ {error}")
            elif results:
                # 데이터프레임 생성
                df = pd.DataFrame(results)
                
                # 급증 지수로 정렬 (이미 정렬되어 있지만 확실히)
                df = df.sort_values('surge_score', ascending=False).reset_index(drop=True)
                
                # 세션 상태에 저장
                st.session_state['df'] = df
                st.session_state['keyword'] = "급증 주제 (최근 7일)"
                st.session_state['total_results'] = len(results)
                st.session_state['trending_mode'] = True
                
                st.success(f"✅ {len(results)}개의 급증 주제를 찾았습니다!")
        
        elif trending_type == "🎯 카테고리별 인기":
            with st.spinner("🎯 카테고리별 인기 영상 수집 중..."):
                results, error = get_trending_videos(api_key, region_code='KR', category_id=category_id, max_results=max_results)
            
            if error:
                st.error(f"❌ {error}")
            elif results:
                # 데이터프레임 생성
                df = pd.DataFrame(results)
                
                # 지표 계산 (트렌딩 영상도 지표 계산 가능)
                with st.spinner("📊 지표 계산 중..."):
                    # 트렌딩 영상은 검색 결과 수를 0으로 설정 (블루오션 지수 계산용)
                    df = calculate_all_metrics(df, 0)
                    df = calculate_cocktail_metrics(df)
                    df = calculate_master_score(df, weights)
                
                # 세션 상태에 저장
                st.session_state['df'] = df
                category_name = selected_category if category_id else "전체"
                st.session_state['keyword'] = f"카테고리별 인기 ({category_name})"
                st.session_state['total_results'] = len(results)
                st.session_state['trending_mode'] = True
                
                st.success(f"✅ {len(results)}개의 인기 영상을 찾았습니다!")
        
        elif trending_type == "💡 키워드 추천":
            # 키워드 추천은 별도 UI로 표시
            st.info("💡 키워드 추천 기능을 사용하려면 먼저 키워드를 검색해주세요.")
            st.session_state['trending_mode'] = False

# 자동 검색 (추천 키워드 클릭 시)
if 'auto_search_keyword' in st.session_state:
    auto_keyword = st.session_state.pop('auto_search_keyword')
    # 검색 실행
    with st.spinner(f"🔍 '{auto_keyword}' 검색 중..."):
        results, total_results, error = search_youtube_enhanced(api_key, auto_keyword, max_results)
    
    if error:
        st.error(f"❌ {error}")
    elif results:
        df = pd.DataFrame(results)
        with st.spinner("📊 지표 계산 중..."):
            df = calculate_all_metrics(df, total_results)
            df = calculate_cocktail_metrics(df)
            df = calculate_master_score(df, weights)
        
        st.session_state['df'] = df
        st.session_state['keyword'] = auto_keyword
        st.session_state['total_results'] = total_results
        st.session_state['trending_mode'] = False
        
        # 키워드 추천
        recommended_keywords, rec_error = get_recommended_keywords(api_key, auto_keyword)
        if recommended_keywords:
            st.session_state['recommended_keywords'] = recommended_keywords
        else:
            st.session_state['recommended_keywords'] = []
        
        st.success(f"✅ {len(results)}개의 영상을 찾았습니다!")

# 검색 실행 및 데이터 저장
if search_button:
    if not api_key:
        st.error("❌ API 키를 입력해주세요.")
    elif not test_keyword:
        st.error("❌ 검색 키워드를 입력해주세요.")
    else:
        with st.spinner("🔍 유튜브에서 검색 및 데이터 수집 중..."):
            results, total_results, error = search_youtube_enhanced(api_key, test_keyword, max_results)
        
        if error:
            st.error(f"❌ {error}")
        elif results:
            # 데이터프레임 생성
            df = pd.DataFrame(results)
            
            # 지표 계산
            with st.spinner("📊 지표 계산 중..."):
                df = calculate_all_metrics(df, total_results)
                df = calculate_cocktail_metrics(df)
                # 현재 가중치로 마스터 점수 계산
                df = calculate_master_score(df, weights)
            
            # 세션 상태에 저장
            st.session_state['df'] = df
            st.session_state['keyword'] = test_keyword
            st.session_state['total_results'] = total_results
            st.session_state['weights'] = weights
            st.session_state['trending_mode'] = False
            
            st.success(f"✅ {len(results)}개의 영상을 찾았습니다!")
            
            # 키워드 추천 표시
            with st.spinner("💡 관련 키워드 추천 중..."):
                recommended_keywords, rec_error = get_recommended_keywords(api_key, test_keyword)
                if recommended_keywords:
                    st.session_state['recommended_keywords'] = recommended_keywords
                else:
                    st.session_state['recommended_keywords'] = []
        else:
            st.warning("⚠️ 검색 결과가 없습니다.")

# 키워드 추천 표시 (검색 모드일 때만)
if 'recommended_keywords' in st.session_state and st.session_state.get('recommended_keywords') and mode == "🔍 키워드 검색":
    st.subheader("💡 추천 키워드")
    keywords = st.session_state['recommended_keywords']
    
    # 키워드를 태그 형태로 표시
    cols = st.columns(min(len(keywords), 5))
    for idx, keyword in enumerate(keywords[:5]):
        with cols[idx % 5]:
            if st.button(f"🔍 {keyword}", key=f"rec_keyword_{idx}", use_container_width=True):
                # 추천 키워드로 재검색
                st.session_state['search_keyword'] = keyword
                st.rerun()
    
    st.markdown("---")

# 데이터가 있으면 랭킹 표시
if 'df' in st.session_state and st.session_state['df'] is not None:
    df = st.session_state['df'].copy()
    keyword = st.session_state.get('keyword', '')
    trending_mode = st.session_state.get('trending_mode', False)
    
    # 가중치가 변경되었거나 최종 마스터 추천이 선택된 경우 마스터 점수 재계산
    if selected_ranking == '최종 마스터 추천':
        # 가중치가 변경되었는지 확인
        weights_changed = st.session_state.get('weights_changed', False)
        if weights_changed or 'master_score' not in df.columns:
            df = calculate_master_score(df, weights)
            # 재계산된 마스터 점수를 세션 상태에 저장 (다음 렌더링을 위해)
            st.session_state['df'] = df
            # 가중치 변경 플래그 리셋 (한 번만 알림 표시)
            if weights_changed:
                st.session_state['weights_changed'] = False
        else:
            # 가중치가 변경되지 않았지만 마스터 점수가 없으면 계산
            if 'master_score' not in df.columns:
                df = calculate_master_score(df, weights)
                st.session_state['df'] = df
    
    # 선택한 랭킹에 따라 정렬
    ranked_df = get_ranking_data(df, selected_ranking)
    
    # 헤더
    if trending_mode:
        if "급증" in keyword:
            st.subheader(f"📈 급증 주제 랭킹")
        elif "카테고리" in keyword:
            st.subheader(f"🎯 카테고리별 인기 랭킹")
        else:
            st.subheader(f"🔥 트렌딩 랭킹")
    else:
        st.subheader(f"🏆 {selected_ranking} 랭킹")
    
    st.caption(f"**{keyword}** | 총 {len(ranked_df)}개 영상")
    
    # 가중치 변경 알림 (최종 마스터 추천 선택 시)
    if selected_ranking == '최종 마스터 추천' and st.session_state.get('weights_changed', False):
        st.info("🔄 가중치가 변경되어 순위가 업데이트되었습니다!")
    
    st.markdown("---")
    
    # 3열 그리드 레이아웃으로 영상 표시
    num_videos = len(ranked_df)
    cols_per_row = 3
    
    for i in range(0, num_videos, cols_per_row):
        cols = st.columns(cols_per_row)
        
        for j, col in enumerate(cols):
            if i + j < num_videos:
                row = ranked_df.iloc[i + j]
                rank = i + j + 1
                
                with col:
                    # 영상 카드
                    with st.container():
                        # 순위 배지
                        badge_color = "#FFD700" if rank == 1 else "#C0C0C0" if rank == 2 else "#CD7F32" if rank == 3 else "#4A90E2"
                        st.markdown(
                            f"""
                            <div style="
                                background-color: {badge_color};
                                color: white;
                                padding: 5px 10px;
                                border-radius: 20px;
                                display: inline-block;
                                font-weight: bold;
                                margin-bottom: 10px;
                            ">{rank}위</div>
                            """,
                            unsafe_allow_html=True
                        )
                        
                        # 썸네일 (클릭 시 영상 페이지로 이동)
                        st.markdown(f"[![Thumbnail]({row['thumbnail']})]({row['url']})")
                        
                        # 제목
                        st.markdown(f"**{row['title'][:50]}{'...' if len(row['title']) > 50 else ''}**")
                        
                        # 채널명 및 구독자 수
                        subscriber_korean = format_korean_number(row['subscriber_count'])
                        st.caption(f"📺 {row['channel_title']} (구독자 {subscriber_korean}명)")
                        
                        # 업로드 일수
                        days_old = int(row['days_old'])
                        if days_old == 0:
                            upload_text = "오늘 업로드"
                        elif days_old == 1:
                            upload_text = "1일 전"
                        elif days_old < 30:
                            upload_text = f"{days_old}일 전"
                        elif days_old < 365:
                            months = days_old // 30
                            upload_text = f"{months}개월 전"
                        else:
                            years = days_old // 365
                            upload_text = f"{years}년 전"
                        
                        # 조회수 (한국어 형식)
                        view_korean = format_korean_number(row['view_count'])
                        
                        # 기본 통계
                        st.markdown(
                            f"""
                            <div style="font-size: 0.9em; color: #333; margin: 5px 0;">
                                <strong>📅 {upload_text}</strong><br>
                                <strong>👁️ 조회수 {view_korean}회</strong><br>
                                👍 {format_korean_number(row['like_count'])} | 💬 {format_korean_number(row['comment_count'])}
                            </div>
                            """,
                            unsafe_allow_html=True
                        )
                        
                        # 추천 이유
                        reason = get_recommendation_reason(row, selected_ranking)
                        st.info(f"💡 {reason}")
                        
                        # 스크립트 복사 버튼
                        script_id = f"script_{row['video_id']}_{rank}".replace('-', '_').replace('.', '_')
                        
                        # 자막 가져오기 버튼
                        transcript_key = f"transcript_{row['video_id']}_{rank}"
                        if transcript_key not in st.session_state:
                            st.session_state[transcript_key] = None
                        
                        col_btn1, col_btn2 = st.columns(2)
                        
                        with col_btn1:
                            if st.button("📋 자막 가져오기", key=f"load_{script_id}", use_container_width=True):
                                with st.spinner("자막을 가져오는 중..."):
                                    transcript_text, error = get_video_transcript(row['video_id'])
                                    if transcript_text:
                                        st.session_state[transcript_key] = transcript_text
                                        st.success("✅ 자막을 가져왔습니다!")
                                    else:
                                        st.session_state[transcript_key] = None
                                        st.warning(f"⚠️ {error}")
                        
                        with col_btn2:
                            # 자막이 있으면 스크립트 생성
                            transcript_text = st.session_state.get(transcript_key)
                            video_script = generate_video_script(row, rank, selected_ranking, transcript_text)
                            
                            # 복사 버튼
                            if st.button("📋 스크립트 복사", key=f"copy_{script_id}", use_container_width=True):
                                st.code(video_script, language=None)
                                st.success("✅ 위 스크립트를 복사하세요! (Ctrl+C 또는 우클릭 > 복사)")
                                
                                # 클립보드 복사 JavaScript
                                script_escaped = json.dumps(video_script, ensure_ascii=False)
                                copy_js = f"""
                                <script>
                                (function() {{
                                    const script = {script_escaped};
                                    navigator.clipboard.writeText(script).then(function() {{
                                        console.log('복사 완료');
                                    }}, function(err) {{
                                        const textArea = document.createElement('textarea');
                                        textArea.value = script;
                                        textArea.style.position = 'fixed';
                                        textArea.style.left = '-999999px';
                                        document.body.appendChild(textArea);
                                        textArea.select();
                                        try {{
                                            document.execCommand('copy');
                                        }} catch (err) {{
                                            console.error('복사 실패');
                                        }}
                                        document.body.removeChild(textArea);
                                    }});
                                }})();
                                </script>
                                """
                                st.markdown(copy_js, unsafe_allow_html=True)
                        
                        # 유튜브 임베드 플레이어
                        video_id = row['video_id']
                        embed_html = f"""
                        <iframe 
                            width="100%" 
                            height="200" 
                            src="https://www.youtube.com/embed/{video_id}" 
                            frameborder="0" 
                            allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture" 
                            allowfullscreen>
                        </iframe>
                        """
                        st.markdown(embed_html, unsafe_allow_html=True)
                        
                        st.markdown("---")
    
    # 지표 설명
    with st.expander("📖 지표 설명"):
        st.markdown("""
        ### 7가지 단일 지표
        - **조회수 효율** 🎯: 영상 조회수 / 채널 구독자 수 (작은 채널이 대박 난 주제 찾기)
        - **급등 에너지** 🔥: 최근 업로드 + 조회수 성장률 근사
        - **블루오션 지수** 🌊: 검색량 / 최근 업로드 영상 수 (수요는 많으나 공급이 적은 곳)
        - **글로벌 트렌드 전이** 🌍: 조회수와 참여도 기반 글로벌 트렌드 가능성
        - **콘텐츠 노후도** 🕰️: 영상 제작 시기 (오래된 영상이 많을수록 기회)
        - **참여 밀도** 💬: (좋아요 + 댓글) / 조회수 (시청자 반응이 뜨거운 주제)
        - **롱테일 확장성** 🔗: 설명/제목 길이 및 댓글 수 기반 확장 가능성
        
        ### 3가지 칵테일 지표
        - **폭발 성장형 (칵테일 A)** 🚀: 급등 에너지 + 글로벌 트렌드 조합
        - **저리스크 침투형 (칵테일 B)** 🏹: 블루오션 + 콘텐츠 노후도 조합
        - **팬덤 형성형 (칵테일 C)** 🤝: 조회수 효율 + 참여 밀도 조합
        
        ### 최종 마스터 추천
        - 위 7가지 지표에 가중치를 부여한 종합 점수
        - 사이드바에서 가중치를 조절하여 실시간으로 순위 변경 가능
        """)

# 초기 안내 메시지
elif not api_key:
    st.info("👈 사이드바에서 YouTube API 키를 입력하고 검색을 시작하세요.")
    st.markdown("""
    ### 📝 사용 방법
    1. 사이드바에 YouTube Data API v3 키를 입력하세요.
    2. 검색할 키워드를 입력하세요.
    3. '검색 실행' 버튼을 클릭하세요.
    
    ### 🔑 API 키 발급 방법
    - [Google Cloud Console](https://console.cloud.google.com/) 접속
    - 프로젝트 생성 또는 선택
    - YouTube Data API v3 활성화
    - API 키 생성
    """)

