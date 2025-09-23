import requests
from bs4 import BeautifulSoup
from googlesearch import search
import os   
import re
import time
import concurrent.futures
from collections import defaultdict
from urllib.parse import urlparse, urljoin
import threading
from urllib.robotparser import RobotFileParser
from config import *

# robots.txt 확인 설정
ROBOTS_CHECK_ENABLED = True  # robots.txt 확인 활성화
ROBOTS_TIMEOUT = 10  # robots.txt 요청 타임아웃

# 크롤링 제한 설정
MAX_CRAWL_LIMIT = 70  # 최대 크롤링 개수 제한

def check_robots_txt(url):
    """robots.txt 확인하여 스크래핑 허용 여부 판단"""
    if not ROBOTS_CHECK_ENABLED:
        return True, "robots.txt 확인 비활성화"
    
    try:
        parsed_url = urlparse(url)
        robots_url = f"{parsed_url.scheme}://{parsed_url.netloc}/robots.txt"
        
        # robots.txt 요청
        response = requests.get(robots_url, timeout=ROBOTS_TIMEOUT)
        
        if response.status_code == 404:
            return True, "robots.txt 없음 (기본 허용)"
        
        if response.status_code != 200:
            return True, f"robots.txt 접근 실패 ({response.status_code})"
        
        # robots.txt 내용 파싱
        robots_content = response.text
        path_analysis = analyze_robots_paths(robots_content, parsed_url.path)
        
        # RobotFileParser로 파싱
        rp = RobotFileParser()
        rp.set_url(robots_url)
        rp.read()
        
        # User-agent: * 에 대한 허용 여부 확인
        can_fetch = rp.can_fetch("*", url)
        
        if can_fetch:
            if path_analysis:
                return True, f"robots.txt 허용 ({path_analysis})"
            else:
                return True, "robots.txt 허용"
        else:
            if path_analysis:
                return False, f"robots.txt 금지 ({path_analysis})"
            else:
                return False, "robots.txt 금지"
            
    except requests.exceptions.Timeout:
        return True, "robots.txt 타임아웃 (기본 허용)"
    except Exception as e:
        return True, f"robots.txt 확인 실패: {str(e)}"

def analyze_robots_paths(robots_content, path):
    """robots.txt에서 경로별 허용/금지 규칙 분석"""
    try:
        if not robots_content:
            return None
        
        # 경로별 규칙을 저장할 딕셔너리
        path_rules = {
            'allowed': [],
            'disallowed': []
        }
        
        lines = robots_content.split('\n')
        current_user_agent = None
        
        for line in lines:
            line = line.strip()
            if not line or line.startswith('#'):
                continue
                
            if line.lower().startswith('user-agent:'):
                current_user_agent = line.split(':', 1)[1].strip()
            elif line.lower().startswith('allow:') and current_user_agent in ['*', None]:
                allowed_path = line.split(':', 1)[1].strip()
                path_rules['allowed'].append(allowed_path)
            elif line.lower().startswith('disallow:') and current_user_agent in ['*', None]:
                disallowed_path = line.split(':', 1)[1].strip()
                path_rules['disallowed'].append(disallowed_path)
        
        # 현재 경로에 대한 규칙 분석
        path_analysis = []
        
        # 허용된 경로 확인
        for allowed_path in path_rules['allowed']:
            if path.startswith(allowed_path) or allowed_path == '/':
                path_analysis.append(f"허용: {allowed_path}")
        
        # 금지된 경로 확인
        for disallowed_path in path_rules['disallowed']:
            if path.startswith(disallowed_path):
                path_analysis.append(f"금지: {disallowed_path}")
        
        # 경로별 우선순위 규칙 적용
        if path_analysis:
            # 더 구체적인 경로가 우선 (긴 경로가 우선)
            allowed_rules = [rule for rule in path_analysis if rule.startswith('허용:')]
            disallowed_rules = [rule for rule in path_analysis if rule.startswith('금지:')]
            
            if allowed_rules and disallowed_rules:
                # 가장 구체적인 규칙 비교
                most_specific_allowed = max(allowed_rules, key=lambda x: len(x.split(':')[1]))
                most_specific_disallowed = max(disallowed_rules, key=lambda x: len(x.split(':')[1]))
                
                allowed_path_len = len(most_specific_allowed.split(':')[1])
                disallowed_path_len = len(most_specific_disallowed.split(':')[1])
                
                if allowed_path_len > disallowed_path_len:
                    return f"경로별 허용 우선: {most_specific_allowed}"
                elif disallowed_path_len > allowed_path_len:
                    return f"경로별 금지 우선: {most_specific_disallowed}"
                else:
                    return f"동일 우선순위: {most_specific_allowed}, {most_specific_disallowed}"
            elif allowed_rules:
                return f"경로별 허용: {', '.join(allowed_rules)}"
            elif disallowed_rules:
                return f"경로별 금지: {', '.join(disallowed_rules)}"
        
        return None
        
    except Exception as e:
        return f"경로 분석 실패: {str(e)}"

def get_links(query, num=30):
    start_time = time.time()
    print(f"\n[+] '{query}' 관련 링크 검색 중... (목표: {num}개)")
    
    try:
        results = []
        all_urls = []
        
        # 더 많은 검색 결과를 수집
        for url in search(query, num_results=num):
            all_urls.append(url)
            if any(domain in url for domain in SEARCH_DOMAINS):
                results.append(url)
                if len(results) >= MAX_SITES:
                    break
        
        # 원하는 도메인이 부족하면 다른 사이트도 추가
        if len(results) < MAX_SITES:
            print(f"[!] 원하는 도메인 사이트가 부족합니다. ({len(results)}개)")
            print(f"[!] 다른 사이트도 추가로 수집합니다...")
            
            for url in all_urls:
                if url not in results and len(results) < MAX_SITES:
                    # 제외할 도메인들
                    exclude_domains = ["youtube.com", "facebook.com", "twitter.com", "instagram.com", "linkedin.com"]
                    if not any(exclude in url for exclude in exclude_domains):
                        results.append(url)
        
        elapsed = time.time() - start_time
        print(f"[+] {len(results)}개 링크 수집 완료 (소요시간: {elapsed:.2f}초)")
        print(f"[+] 검색된 총 URL: {len(all_urls)}개, 필터링 후: {len(results)}개")
        return results
    except Exception as e:
        print(f"[-] 링크 검색 실패: {e}")
        return []

def clean_html_worker(args):
    url, url_index = args
    start_time = time.time()
    
    try:
        if SHOW_DETAILED_PROGRESS:
            print(f"[{url_index+1:2d}] 페이지 파싱 중: {url}")
        
        # 요청 설정
        request_kwargs = {}
        if ENABLE_TIMEOUT:
            request_kwargs['timeout'] = TIMEOUT_SECONDS
        if ENABLE_USER_AGENT:
            request_kwargs['headers'] = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
        
        response = requests.get(url, **request_kwargs)
        response.encoding = response.apparent_encoding  # 인코딩 자동 감지 추가
        soup = BeautifulSoup(response.text, "html.parser")
        
        # 불필요한 태그 제거
        for tag in soup(["script", "style", "footer", "nav", "form", "header", "aside", "iframe"]):
            tag.decompose()
        
        # 텍스트 추출 및 정리
        text = soup.get_text(separator=" ", strip=True)
        # 한글, 영문, 숫자, 공백, 일부 특수문자만 남기기
        text = re.sub(r'[^가-힣a-zA-Z0-9 .,!?\n\r\t]', '', text)
        
        elapsed = time.time() - start_time
        if SHOW_DETAILED_PROGRESS:
            print(f"[{url_index+1:2d}] ✓ 성공: {url} (소요시간: {elapsed:.2f}초)")
        
        return {
            'url': url,
            'text': text,
            'success': True,
            'elapsed': elapsed,
            'error': None
        }
        
    except requests.exceptions.Timeout:
        elapsed = time.time() - start_time
        if SHOW_DETAILED_PROGRESS:
            print(f"[{url_index+1:2d}] ✗ 타임아웃: {url} (소요시간: {elapsed:.2f}초)")
        return {
            'url': url,
            'text': "",
            'success': False,
            'elapsed': elapsed,
            'error': '타임아웃'
        }
    except Exception as e:
        elapsed = time.time() - start_time
        if SHOW_DETAILED_PROGRESS:
            print(f"[{url_index+1:2d}] ✗ 실패: {url} - {e} (소요시간: {elapsed:.2f}초)")
        return {
            'url': url,
            'text': "",
            'success': False,
            'elapsed': elapsed,
            'error': str(e)
        }

def check_robots_for_urls(urls):
    """URL 목록에 대해 robots.txt 확인"""
    print(f"\n[+] robots.txt 확인 중... ({len(urls)}개 사이트)")
    
    robots_results = []
    for i, url in enumerate(urls):
        domain = urlparse(url).netloc
        print(f"[{i+1:2d}] robots.txt 확인: {domain}")
        
        is_allowed, reason = check_robots_txt(url)
        robots_results.append({
            'url': url,
            'domain': domain,
            'allowed': is_allowed,
            'reason': reason
        })
        
        status = "✅ 허용" if is_allowed else "❌ 금지"
        print(f"[{i+1:2d}] {status}: {domain} - {reason}")
    
    return robots_results

def filter_urls_by_robots(robots_results):
    """robots.txt 결과에 따라 URL 필터링 및 사용자 선택"""
    print(f"\n" + "="*60)
    print("🤖 robots.txt 필터링 결과")
    print("="*60)
    
    allowed_urls = [r for r in robots_results if r['allowed']]
    blocked_urls = [r for r in robots_results if not r['allowed']]
    
    print(f"📊 총 {len(robots_results)}개 사이트 분석 완료")
    print(f"✅ 스크래핑 허용: {len(allowed_urls)}개")
    print(f"❌ 스크래핑 금지: {len(blocked_urls)}개")
    
    # 크롤링 제한 확인
    if len(allowed_urls) > MAX_CRAWL_LIMIT:
        print(f"\n⚠️  허용된 사이트가 {MAX_CRAWL_LIMIT}개를 초과합니다.")
        print(f"   최대 {MAX_CRAWL_LIMIT}개까지만 처리 가능합니다.")
        allowed_urls = allowed_urls[:MAX_CRAWL_LIMIT]
        print(f"   상위 {MAX_CRAWL_LIMIT}개 사이트만 선택됩니다.")
    
    if len(blocked_urls) > 0:
        print(f"\n❌ 스크래핑 금지된 사이트들:")
        for i, result in enumerate(blocked_urls, 1):
            print(f"  {i:2d}. {result['domain']} - {result['reason']}")
    
    if len(allowed_urls) == 0:
        print("\n⚠️  스크래핑이 허용된 사이트가 없습니다.")
        choice = input("금지된 사이트도 포함하여 진행하시겠습니까? (y/n): ").strip().lower()
        if choice == 'y':
            # 금지된 사이트도 포함하되 제한 적용
            all_urls = [r['url'] for r in robots_results]
            if len(all_urls) > MAX_CRAWL_LIMIT:
                print(f"⚠️  모든 사이트가 {MAX_CRAWL_LIMIT}개를 초과합니다.")
                all_urls = all_urls[:MAX_CRAWL_LIMIT]
            return all_urls
        else:
            return []
    
    print(f"\n✅ 스크래핑 허용된 사이트들 (최대 {MAX_CRAWL_LIMIT}개):")
    for i, result in enumerate(allowed_urls, 1):
        print(f"  {i:2d}. {result['domain']} - {result['reason']}")
    
    print(f"\n" + "-"*60)
    print("필터링 옵션:")
    print("1. 허용된 사이트만 처리")
    print("2. 모든 사이트 처리 (금지된 사이트 포함)")
    print("3. 수동 선택")
    print("0. 취소")
    
    while True:
        try:
            choice = input("\n선택하세요 (0-3): ").strip()
            
            if choice == "0":
                return []
            elif choice == "1":
                print(f"✅ 허용된 사이트 {len(allowed_urls)}개 선택됨")
                return [r['url'] for r in allowed_urls]
            elif choice == "2":
                # 모든 사이트 선택 시에도 제한 적용
                all_urls = [r['url'] for r in robots_results]
                if len(all_urls) > MAX_CRAWL_LIMIT:
                    print(f"⚠️  모든 사이트가 {MAX_CRAWL_LIMIT}개를 초과합니다.")
                    all_urls = all_urls[:MAX_CRAWL_LIMIT]
                    print(f"   상위 {MAX_CRAWL_LIMIT}개 사이트만 선택됩니다.")
                print(f"✅ 모든 사이트 {len(all_urls)}개 선택됨")
                return all_urls
            elif choice == "3":
                return manual_url_selection(allowed_urls)
            else:
                print("❌ 잘못된 선택입니다. 0-3 중 선택해주세요.")
        except KeyboardInterrupt:
            print("\n❌ 취소되었습니다.")
            return []

def manual_url_selection(allowed_urls):
    """수동 URL 선택"""
    print(f"\n📝 수동 선택 모드 (허용된 사이트 {len(allowed_urls)}개, 최대 {MAX_CRAWL_LIMIT}개 선택 가능)")
    print("처리할 사이트 번호를 쉼표로 구분하여 입력하세요 (예: 1,3,5)")
    print("또는 'all' 입력 시 모든 허용된 사이트 선택")
    
    while True:
        try:
            choice = input("선택: ").strip()
            
            if choice.lower() == 'all':
                # 최대 제한 적용
                if len(allowed_urls) > MAX_CRAWL_LIMIT:
                    print(f"⚠️  모든 사이트가 {MAX_CRAWL_LIMIT}개를 초과합니다.")
                    selected_urls = [r['url'] for r in allowed_urls[:MAX_CRAWL_LIMIT]]
                    print(f"   상위 {MAX_CRAWL_LIMIT}개 사이트만 선택됩니다.")
                else:
                    selected_urls = [r['url'] for r in allowed_urls]
                print(f"✅ 선택된 사이트 {len(selected_urls)}개")
                return selected_urls
            
            # 번호 파싱
            selected_indices = [int(x.strip()) - 1 for x in choice.split(',')]
            selected_urls = []
            
            for idx in selected_indices:
                if 0 <= idx < len(allowed_urls):
                    selected_urls.append(allowed_urls[idx]['url'])
                else:
                    print(f"⚠️  잘못된 번호: {idx + 1}")
            
            # 최대 제한 확인
            if len(selected_urls) > MAX_CRAWL_LIMIT:
                print(f"⚠️  선택한 사이트가 {MAX_CRAWL_LIMIT}개를 초과합니다.")
                selected_urls = selected_urls[:MAX_CRAWL_LIMIT]
                print(f"   상위 {MAX_CRAWL_LIMIT}개 사이트만 선택됩니다.")
            
            if selected_urls:
                print(f"✅ 선택된 사이트 {len(selected_urls)}개:")
                for i, url in enumerate(selected_urls, 1):
                    domain = urlparse(url).netloc
                    print(f"  {i}. {domain}")
                return selected_urls
            else:
                print("❌ 선택된 사이트가 없습니다. 다시 선택해주세요.")
                
        except (ValueError, KeyboardInterrupt):
            print("❌ 잘못된 입력입니다. 다시 시도해주세요.")

def clean_html_parallel(urls):
    start_time = time.time()
    print(f"\n[+] 병렬 처리로 {len(urls)}개 사이트 크롤링 시작...")
    
    if ENABLE_PARALLEL:
        results = []
        with concurrent.futures.ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
            # URL과 인덱스를 함께 전달
            future_to_url = {executor.submit(clean_html_worker, (url, i)): url for i, url in enumerate(urls)}
            
            for future in concurrent.futures.as_completed(future_to_url):
                result = future.result()
                results.append(result)
    else:
        # 순차 처리
        results = []
        for i, url in enumerate(urls):
            result = clean_html_worker((url, i))
            results.append(result)
    
    total_time = time.time() - start_time
    print(f"[+] 크롤링 완료 (총 소요시간: {total_time:.2f}초)")
    
    return results

def filter_noise(text):
    ad_patterns = [
        r"배너\s?(광고|클릭)", r"광고문의", r"마케팅\s?문의",
        r"제휴\s?(문의|링크)", r"구매\s?링크", r"프로모션", r"스폰서", r"광고\s?수익",
        r"후원\s?(계좌|링크|문의|해주시면|받습니다|바랍니다)", r"아래.*후원", r"후원해\s?주세요",
        r"협찬\s?(문의|링크|해주시면)", r"쿠팡\s?파트너스", r"구매링크",
        r"이 글은 .*? 광고를 포함하고 있습니다",
        r"이 포스트는 .*? 후원을 받고 작성되었습니다",
        r"광고성 문구", r"유료 광고", r"제휴 마케팅", r"체험단",
        r"Sponsored by", r"이벤트 참여", r"이벤트 안내", r"채널 가입"
    ]
    ad_regex = re.compile("|".join(ad_patterns), re.IGNORECASE)
    lines = text.split('\n')
    filtered = []
    for line in lines:
        line_stripped = line.strip()
        # 1. 너무 짧은 줄 제거
        if len(line_stripped) <= 30:
            continue
        # 2. 광고/스팸 패턴 제거
        if ad_regex.search(line_stripped):
            continue
        # 3. 이메일, 오픈채팅, 연락처 등 제거
        if re.search(r'([a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+)|(오픈채팅)|(카톡)|(연락처)|(문의:)', line_stripped):
            continue
        # 4. 알파벳/숫자 비율이 80% 이상이면 제거 (난수/해시/코드 등)
        if len(line_stripped) > 10:
            ratio = sum(c.isalnum() for c in line_stripped) / len(line_stripped)
            if ratio > 0.8:
                continue
        filtered.append(line_stripped)
    return "\n".join(filtered)

def print_texts(text_list, url_list):
    """수집된 텍스트를 print문으로 출력"""
    print("\n" + "="*80)
    print("📄 수집된 텍스트 데이터")
    print("="*80)
    
    for i, (text, url) in enumerate(zip(text_list, url_list)):
        print(f"\n[문서 {i+1}] (URL: {url})")
        print("-" * 60)
        print(text)
        print("-" * 60)
    
    print(f"\n[+] 총 {len(text_list)}개 문서 출력 완료")

def simple_text_search(texts, urls, query, k=5):
    """간단한 키워드 기반 텍스트 검색"""
    print(f"\n[+] \"{query}\"로 텍스트 검색 Top-{k}")
    
    # 검색어를 키워드로 분리
    keywords = query.lower().split()
    
    # 각 텍스트에 대한 점수 계산
    scores = []
    for i, text in enumerate(texts):
        text_lower = text.lower()
        score = 0
        
        # 키워드 매칭 점수 계산
        for keyword in keywords:
            if keyword in text_lower:
                score += text_lower.count(keyword)
        
        # 텍스트 길이로 정규화 (짧은 텍스트에 가중치)
        score = score / (len(text) / 1000 + 1)
        
        scores.append((score, i, text, urls[i]))
    
    # 점수순으로 정렬
    scores.sort(reverse=True)
    
    # 상위 k개 결과 출력
    for i, (score, doc_idx, text, url) in enumerate(scores[:k]):
        if score > 0:
            print(f"\n--- 결과 {i+1} (점수: {score:.2f}) ---")
            print(f"URL: {url}")
            print(f"내용: {text[:400]}...")
        else:
            break
    
    if not any(score > 0 for score, _, _, _ in scores[:k]):
        print("검색 결과가 없습니다.")

def analyze_failures(crawl_results):
    """실패 원인 분석"""
    if not SHOW_FAILURE_ANALYSIS:
        return
        
    print("\n====== [실패 원인 분석] ======")
    
    success_count = sum(1 for r in crawl_results if r['success'])
    failure_count = len(crawl_results) - success_count
    
    print(f"성공: {success_count}개, 실패: {failure_count}개")
    
    if failure_count > 0:
        error_types = defaultdict(int)
        for result in crawl_results:
            if not result['success']:
                error_types[result['error']] += 1
        
        print("\n실패 원인별 통계:")
        for error, count in error_types.items():
            print(f"- {error}: {count}개")
    
    print("===============================")

if __name__ == "__main__":
    total_start_time = time.time()
    
    # 설정 확인
    print(f"=== 설정 정보 ===")
    print(f"최대 사이트 개수: {MAX_SITES}")
    print(f"최대 크롤링 개수: {MAX_CRAWL_LIMIT}개")
    print(f"타임아웃: {TIMEOUT_SECONDS}초")
    print(f"동시 처리 스레드: {MAX_WORKERS}개")
    print(f"최소 텍스트 길이: {MIN_TEXT_LENGTH}자")
    print(f"robots.txt 확인: {'활성화' if ROBOTS_CHECK_ENABLED else '비활성화'}")
    print("================")
    
    query = input("검색할 주제를 입력하세요: ").strip()
    
    # 1단계: 링크 수집
    print(f"\n=== 1단계: 링크 수집 ===")
    urls = get_links(query, num=MAX_SITES * SEARCH_MULTIPLIER)  # 여유있게 검색
    
    if not urls:
        print("[-] 링크를 수집하지 못했습니다.")
        exit()
    
    print(f"[+] 수집된 URL 개수: {len(urls)}개")
    
    # 1.5단계: robots.txt 확인 및 필터링
    if ROBOTS_CHECK_ENABLED:
        print(f"\n=== 1.5단계: robots.txt 확인 ===")
        robots_results = check_robots_for_urls(urls)
        filtered_urls = filter_urls_by_robots(robots_results)
        
        if not filtered_urls:
            print("[-] 처리할 사이트가 선택되지 않았습니다.")
            exit()
        
        urls = filtered_urls
        print(f"[+] 필터링 후 URL 개수: {len(urls)}개")
    
    # 2단계: 병렬 크롤링
    print(f"\n=== 2단계: 웹 크롤링 ===")
    crawl_results = clean_html_parallel(urls)
    
    # 3단계: 텍스트 필터링 및 저장
    print(f"\n=== 3단계: 텍스트 필터링 ===")
    texts = []
    used_urls = []
    failed_urls = []
    
    domain_count_raw = defaultdict(int)
    domain_count_final = defaultdict(int)
    
    print(f"[+] 크롤링 결과 분석 중...")
    for i, result in enumerate(crawl_results):
        url = result['url']
        domain = urlparse(url).netloc
        domain_count_raw[domain] += 1
        
        if result['success']:
            filtered = filter_noise(result['text'])
            if len(filtered) > MIN_TEXT_LENGTH:
                texts.append(filtered)
                used_urls.append(url)
                domain_count_final[domain] += 1
                print(f"[{i+1:2d}] ✓ 성공: {domain} (텍스트 길이: {len(filtered)}자)")
            else:
                failed_urls.append((url, f"텍스트 길이 부족 ({len(filtered)}자)"))
                print(f"[{i+1:2d}] ✗ 실패: {domain} (텍스트 길이: {len(filtered)}자)")
        else:
            failed_urls.append((url, result['error']))
            print(f"[{i+1:2d}] ✗ 실패: {domain} ({result['error']})")
    
    print(f"[+] 필터링 완료: {len(texts)}개 문서 통과")
    
    # 실패 원인 분석
    analyze_failures(crawl_results)
    
    if not texts:
        print("[-] 충분한 문서를 수집하지 못했습니다.")
        exit()
    
    # 4단계: 텍스트 출력
    print_texts(texts, used_urls)
    
    total_time = time.time() - total_start_time
    
    print("\n====== [수집 요약] ======")
    print(f"총 {len(urls)}개 사이트 크롤링 시도, {len(texts)}개 문서 필터 통과 및 출력")
    print(f"전체 소요시간: {total_time:.2f}초")
    print("== 사이트별 (시도 → 최종 출력):")
    for domain in sorted(domain_count_raw, key=lambda d: -domain_count_final[d]):
        tried = domain_count_raw[domain]
        saved = domain_count_final[domain]
        print(f"- {domain}: {tried}개 시도 → {saved}개 출력")
    
    if failed_urls:
        print("\n== 실패한 사이트들:")
        for url, reason in failed_urls[:MAX_FAILURE_DISPLAY]:  # 설정된 개수만큼 표시
            print(f"- {url}: {reason}")
        if len(failed_urls) > MAX_FAILURE_DISPLAY:
            print(f"... 외 {len(failed_urls) - MAX_FAILURE_DISPLAY}개") 
    
    print("=========================")
    
    # 5단계: 간단한 텍스트 검색
    while True:
        q = input('\n검색할 키워드를 입력하세요(엔터만 누르면 종료): ').strip()
        if not q:
            break
        simple_text_search(texts, used_urls, q, k=5)    