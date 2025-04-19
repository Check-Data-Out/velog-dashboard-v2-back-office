#!/usr/bin/env python
"""
게시글 데이터 마이그레이션 스크립트

원격/운영 데이터베이스에서 로컬 데이터베이스로 Post 테이블 데이터를 이관합니다.
"""

from django.db import connections, transaction

from posts.models import Post
from users.models import User

print("게시글 마이그레이션을 시작합니다...")

try:
    # 청크 크기 설정
    chunk_size = 500
    offset = 0
    total_migrated = 0
    success_count = 0
    update_count = 0
    skipped_count = 0

    while True:
        # 원격 DB에서 게시글 데이터를 청크 단위로 가져오기
        with connections["prod"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT p.id, p.created_at, p.updated_at, p.post_uuid, p.user_id, 
                       p.title, p.is_active, p.slug, p.released_at, u.velog_uuid
                FROM posts_post p
                JOIN users_user u ON p.user_id = u.id
                ORDER BY p.id
                LIMIT {chunk_size} OFFSET {offset}
            """
            )
            posts = cursor.fetchall()

        if not posts:
            break

        print(f"게시글 데이터 {len(posts)}개 처리 중 (오프셋 {offset})...")

        # 로컬 DB에 데이터 삽입
        with transaction.atomic():
            for post in posts:
                # 게시글이 이미 로컬에 존재하는지 확인
                existing_post = Post.objects.filter(post_uuid=post[3]).first()

                # velog_uuid를 이용해 로컬 사용자 찾기
                velog_uuid = post[9]  # velog_uuid는 10번째 컬럼

                try:
                    user = User.objects.get(velog_uuid=velog_uuid)
                except User.DoesNotExist:
                    print(
                        f"UUID {velog_uuid}의 사용자가 로컬에 존재하지 않습니다. 게시글 {post[3]} 건너뜁니다."
                    )
                    skipped_count += 1
                    continue

                if existing_post:
                    print(
                        f"UUID {post[3]}의 게시글이 이미 존재합니다. 정보를 업데이트합니다..."
                    )
                    # 기존 게시글 정보 업데이트
                    existing_post.title = post[5]
                    existing_post.is_active = post[6]
                    existing_post.slug = post[7]
                    existing_post.released_at = post[8]
                    existing_post.save()
                    update_count += 1
                else:
                    print(f"UUID {post[3]}의 새 게시글을 생성합니다.")
                    # 새 게시글 생성
                    Post.objects.create(
                        created_at=post[1],
                        updated_at=post[2],
                        post_uuid=post[3],
                        user=user,
                        title=post[5],
                        is_active=post[6],
                        slug=post[7],
                        released_at=post[8],
                    )
                    success_count += 1

        total_migrated += len(posts)
        offset += chunk_size
        print(
            f"현재까지 {total_migrated}개의 게시글을 마이그레이션했습니다..."
        )

    print(
        f"게시글 마이그레이션이 완료되었습니다. 새로 생성: {success_count}개, 업데이트: {update_count}개, 건너뜀: {skipped_count}개"
    )
    print(f"총 처리된 레코드: {total_migrated}개")

except Exception as e:
    print(f"게시글 마이그레이션 중 오류 발생: {e}")
