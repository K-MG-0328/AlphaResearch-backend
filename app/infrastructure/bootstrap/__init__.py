"""부팅 시 1회 실행되는 초기화 작업 모음.

main.py 의 lifespan 부담을 분리. 외부에서는 다음 두 entrypoint 만 사용:

- ``orm_imports``: SQLAlchemy 메타데이터에 ORM 모델을 등록하기 위한 ``noqa: F401`` 일괄 import 모듈
- ``startup_jobs.run_all_bootstraps``: lifespan 의 모든 부트스트랩 작업을 순서대로 실행
- ``startup_jobs.start_scheduler``: APScheduler 인스턴스 생성·시작
"""
