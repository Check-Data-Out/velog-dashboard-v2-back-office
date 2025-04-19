#!/usr/bin/env python
"""
게시글 통계 데이터 마이그레이션 스크립트

원격/운영 데이터베이스에서 로컬 데이터베이스로 PostDailyStatistics 테이블 데이터를 이관합니다.
"""

from django.db import connections, transaction

from posts.models import Post, PostDailyStatistics

print("게시글 통계 마이그레이션을 시작합니다...")

try:
    # 청크 크기 설정
    chunk_size = 1000
    offset = 0
    total_migrated = 0
    new_count = 0
    update_count = 0
    skipped_count = 0

    while True:
        # 원격 DB에서 통계 데이터를 청크 단위로 가져오기 (post_uuid와 함께)
        with connections["prod"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT pds.id, pds.created_at, pds.updated_at, pds.post_id, pds.date, 
                       pds.daily_view_count, pds.daily_like_count, p.post_uuid
                FROM posts_postdailystatistics pds
                JOIN posts_post p ON pds.post_id = p.id
                WHERE pds.date >= CURRENT_DATE - INTERVAL '3 days'
                ORDER BY pds.id
                LIMIT {chunk_size} OFFSET {offset}
            """
            )
            stats_chunk = cursor.fetchall()

        if not stats_chunk:
            break

        print(f"통계 데이터 {len(stats_chunk)}개 처리 중 (오프셋 {offset})...")

        # 로컬 DB에 데이터 삽입
        with transaction.atomic():
            for stat in stats_chunk:
                # post_uuid를 이용해 로컬 게시글 찾기
                post_uuid = stat[7]  # post_uuid는 8번째 컬럼

                try:
                    post = Post.objects.get(post_uuid=post_uuid)
                except Post.DoesNotExist:
                    print(
                        f"UUID {post_uuid}의 게시글이 로컬에 존재하지 않습니다. 통계 {stat[0]} 건너뜁니다."
                    )
                    skipped_count += 1
                    continue

                # 통계가 이미 로컬에 존재하는지 확인 (post 객체와 date로 찾기)
                existing_stat = PostDailyStatistics.objects.filter(
                    post=post, date=stat[4]
                ).first()

                if existing_stat:
                    # 기존 통계 정보 업데이트
                    existing_stat.daily_view_count = stat[5]
                    existing_stat.daily_like_count = stat[6]
                    existing_stat.save()
                    update_count += 1
                else:
                    # 새 통계 생성
                    PostDailyStatistics.objects.create(
                        id=stat[0],
                        created_at=stat[1],
                        updated_at=stat[2],
                        post=post,  # 로컬 post 객체 사용
                        date=stat[4],
                        daily_view_count=stat[5],
                        daily_like_count=stat[6],
                    )
                    new_count += 1

        total_migrated += len(stats_chunk)
        offset += chunk_size
        print(
            f"현재까지 {total_migrated}개의 통계 데이터를 마이그레이션했습니다..."
        )

    print(
        f"게시글 통계 마이그레이션이 완료되었습니다. 새로 생성: {new_count}개, 업데이트: {update_count}개, 건너뜀: {skipped_count}개"
    )
    print(f"총 처리된 레코드: {total_migrated}개")

except Exception as e:
    print(f"게시글 통계 마이그레이션 중 오류 발생: {e}")
