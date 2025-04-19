#!/usr/bin/env python
"""
사용자 데이터 마이그레이션 스크립트

원격/운영 데이터베이스에서 로컬 데이터베이스로 User 테이블 데이터를 이관합니다.
"""

from django.db import connections, transaction

from users.models import User

print("사용자 마이그레이션을 시작합니다...")

try:
    # 청크 크기 설정 (메모리 문제 방지를 위해)
    chunk_size = 500
    offset = 0
    total_migrated = 0
    success_count = 0
    update_count = 0

    while True:
        # 원격 DB에서 사용자 데이터를 청크 단위로 가져오기
        with connections["prod"].cursor() as cursor:
            cursor.execute(
                f"""
                SELECT id, created_at, updated_at, velog_uuid, access_token, 
                       refresh_token, group_id, email, is_active 
                FROM users_user
                ORDER BY id
                LIMIT {chunk_size} OFFSET {offset}
            """
            )
            users = cursor.fetchall()

        if not users:
            break

        print(f"사용자 데이터 {len(users)}명 처리 중 (오프셋 {offset})...")

        # 로컬 DB에 데이터 삽입
        with transaction.atomic():
            for user in users:
                # 사용자가 이미 로컬에 존재하는지 확인
                existing_user = User.objects.filter(velog_uuid=user[3]).first()

                if existing_user:
                    print(
                        f"UUID {user[3]}의 사용자가 이미 존재합니다. 정보를 업데이트합니다..."
                    )
                    # 기존 사용자 정보 업데이트
                    existing_user.access_token = user[4]
                    existing_user.refresh_token = user[5]
                    existing_user.group_id = user[6]
                    existing_user.email = user[7]
                    existing_user.is_active = user[8]
                    existing_user.save()
                    update_count += 1
                else:
                    print(f"UUID {user[3]}의 새 사용자를 생성합니다.")
                    # 새 사용자 생성
                    User.objects.create(
                        created_at=user[1],
                        updated_at=user[2],
                        velog_uuid=user[3],
                        access_token=user[4],
                        refresh_token=user[5],
                        group_id=user[6],
                        email=user[7],
                        is_active=user[8],
                    )
                    success_count += 1

        total_migrated += len(users)
        offset += chunk_size
        print(
            f"현재까지 {total_migrated}명의 사용자를 마이그레이션했습니다..."
        )

    print(
        f"사용자 마이그레이션이 완료되었습니다. 새로 생성: {success_count}명, 업데이트: {update_count}명"
    )
    print(f"총 처리된 사용자: {total_migrated}명")

except Exception as e:
    print(f"사용자 마이그레이션 중 오류 발생: {e}")
