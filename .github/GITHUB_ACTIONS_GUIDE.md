# 🚀 GitHub Actions 완전 무료 자동화 가이드

**완전 무료**, **영구 사용 가능**, **정해진 시간 자동 실행**

---

## ✨ 특징

- ✅ **완전 무료**: 월 2,000분 무료 (Private repo도 가능)
- ✅ **자동 실행**: 매일 정해진 시간(Asia/Seoul)에 자동 실행
- ✅ **서버 불필요**: GitHub 서버에서 실행
- ✅ **간편한 설정**: 5분 안에 완료
- ✅ **결과물 자동 저장**: Artifacts로 7일간 보관

---

## ⏰ 자동 실행 스케줄

| 워크플로우 | 실행 시간 (KST) | 파일 |
|-----------|----------------|------|
| 🔬 과학 | **매일 오전 9시** | `daily-science.yml` |
| ♟️ 체스 | **매일 오후 2시** | `daily-chess.yml` |
| 📜 역사 | **매일 오후 7시** | `daily-history.yml` |
| 🧪 테스트 | **수동 실행** | `manual-test.yml` |

---

## 🎯 5분 안에 시작하기

### 1단계: GitHub Repository Secrets 설정

1. **GitHub Repository 이동**
2. **Settings** → **Secrets and variables** → **Actions**
3. **New repository secret** 클릭
4. 다음 4개 Secret 추가:

| Secret Name | 값 | 설명 |
|-------------|-----|------|
| `OPENAI_API_KEY` | `sk-proj-...` | OpenAI API 키 |
| `GOOGLE_API_KEY` | `AIza...` | Google API 키 (Gemini) |
| `AWS_ACCESS_KEY_ID` | `AKIA...` | AWS Polly TTS용 |
| `AWS_SECRET_ACCESS_KEY` | `...` | AWS Secret Key |

**설정 화면 예시:**
```
Name: OPENAI_API_KEY
Secret: sk-proj-1234567890abcdef...
```

---

### 2단계: 코드 Push (자동 설정됨)

```bash
# 이미 .github/workflows/ 폴더가 포함되어 있습니다!
git push origin main
```

Push하면 자동으로 GitHub Actions가 활성화됩니다.

---

### 3단계: 테스트 실행

1. **GitHub Repository** → **Actions** 탭 이동
2. **🧪 수동 테스트 실행** 워크플로우 선택
3. **Run workflow** 클릭
4. 작업 선택 (과학/체스/역사)
5. **Run workflow** 버튼 클릭

5-10분 후 영상 생성 완료!

---

## 📥 결과물 다운로드

### Actions Artifacts에서 다운로드

1. **Actions** 탭 → 완료된 워크플로우 클릭
2. 하단 **Artifacts** 섹션
3. `science-video-123` 다운로드
4. ZIP 압축 해제 → MP4 파일 확인

**보관 기간**: 7일 (자동 삭제)

---

## 🔧 시간 변경 방법

### Cron 표현식 수정

`.github/workflows/daily-science.yml` 파일:

```yaml
on:
  schedule:
    - cron: '0 0 * * *'  # UTC 00:00 = KST 09:00
```

| 원하는 KST 시간 | Cron 표현식 | 설명 |
|---------------|-------------|------|
| 오전 6시 | `cron: '0 21 * * *'` | UTC -9시간 |
| 오전 9시 | `cron: '0 0 * * *'` | 기본값 |
| 정오 12시 | `cron: '0 3 * * *'` | |
| 오후 6시 | `cron: '0 9 * * *'` | |
| 자정 00시 | `cron: '0 15 * * *'` | |

**주의**: GitHub Actions는 UTC 시간 기준!  
**KST = UTC + 9시간**

---

## 💰 비용 계산

### GitHub Actions 무료 한도

| 플랜 | 월 무료 시간 | 비용 |
|------|-------------|------|
| **Public Repo** | **무제한** | **$0** 🎉 |
| **Private Repo** | 2,000분 | $0 |
| Private 초과 시 | 분당 $0.008 | 거의 없음 |

### 예상 사용량

- 영상 1개 생성: **10분**
- 하루 3개 영상: **30분**
- **월 사용량: 900분** (2,000분 내)

**결론: 완전 무료!** ✨

---

## 🎬 자동 YouTube 업로드 (선택)

현재는 Artifacts로 다운로드 → 수동 업로드

### 자동 업로드 추가 방법

1. YouTube Data API 활성화
2. OAuth 2.0 Credentials 생성
3. `upload.py` 수정 (Headless 모드)
4. GitHub Secrets에 YouTube 토큰 추가

**가이드 추가가 필요하면 말씀해주세요!**

---

## 📊 모니터링

### GitHub Actions 실행 상태 확인

1. **Actions** 탭
2. 최근 실행 내역 확인
3. 성공 ✅ / 실패 ❌ 표시
4. 로그 클릭하여 상세 확인

### 이메일 알림 (실패 시)

- GitHub 계정 이메일로 자동 전송
- Settings → Notifications에서 설정 가능

---

## 🔍 문제 해결

### 1. 워크플로우가 실행되지 않음

**원인**: Secrets 미설정  
**해결**: Settings → Secrets에서 4개 키 확인

### 2. 영상 생성 실패

**확인 방법**:
1. Actions → 실패한 워크플로우 클릭
2. 로그 확인
3. API 키 오류인지 확인

**해결**:
- Secrets 값 재확인
- API 키 할당량 확인

### 3. 시간이 안 맞음

**원인**: Cron은 UTC 기준  
**해결**: KST = UTC + 9시간으로 계산

---

## 🚀 고급 기능

### 여러 채널 동시 운영

각 채널별로 워크플로우 복사:

```bash
.github/workflows/
├── channel1-science.yml  # 채널1 과학
├── channel1-chess.yml    # 채널1 체스
├── channel2-science.yml  # 채널2 과학
└── ...
```

### 주간 실행 (매일 → 주 1회)

```yaml
on:
  schedule:
    - cron: '0 0 * * 1'  # 매주 월요일 오전 9시
```

---

## 📋 체크리스트

설정 완료 확인:

- [ ] GitHub Secrets 4개 등록 완료
- [ ] `.github/workflows/` 파일 Push 완료
- [ ] 수동 테스트 실행 성공
- [ ] Artifacts 다운로드 확인
- [ ] 자동 스케줄 확인 (다음날 실행 대기)

---

## 🎉 완료!

이제 **GitHub Actions**가 매일 정해진 시간에 자동으로 영상을 생성합니다!

- ✅ **완전 무료** (월 2,000분)
- ✅ **서버 관리 불필요**
- ✅ **정확한 시간 실행** (Asia/Seoul)
- ✅ **결과물 자동 저장** (7일)

**AWS EC2/ECS 필요 없이 GitHub만으로 완전 자동화!** 🚀

---

## 💡 추가 질문

- YouTube 자동 업로드 가이드 필요?
- 다른 시간대 설정 도움?
- 에러 발생 시 로그 분석?

언제든 물어보세요! 😊
