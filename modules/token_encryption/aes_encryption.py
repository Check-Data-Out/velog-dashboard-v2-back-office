import os
from base64 import b64decode, b64encode

from cryptography.hazmat.backends import default_backend
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes


# AES 암호화/복호화 클래스
class AESEncryption:
    def __init__(self, key: bytes):
        """
        key: 256-bit (32 bytes) 암호화 키
        """
        if len(key) != 32:
            raise ValueError("Key must be 256 bits (32 bytes).")
        self.key = key

    def encrypt(self, plaintext: str) -> str:
        """
        AES 암호화를 수행합니다.
        :param plaintext: 암호화할 문자열
        :return: base64로 인코딩된 암호화 데이터
        """
        iv = os.urandom(16)  # 16-byte IV 생성
        cipher = Cipher(
            algorithms.AES(self.key), modes.CBC(iv), backend=default_backend()
        )
        encryptor = cipher.encryptor()

        # PKCS7 패딩 처리
        padded_data = self._pad(plaintext.encode())
        encrypted_data = encryptor.update(padded_data) + encryptor.finalize()

        # IV와 암호화 데이터를 결합하여 반환
        return b64encode(iv + encrypted_data).decode()

    def decrypt(self, encrypted_data: str) -> str:
        """
        AES 복호화를 수행합니다.
        :param encrypted_data: base64로 인코딩된 암호화 데이터
        :return: 복호화된 문자열
        """
        _encrypted_data: bytes = b64decode(encrypted_data)
        iv = _encrypted_data[:16]  # 암호화 데이터에서 IV 추출
        encrypted_content = _encrypted_data[16:]

        cipher = Cipher(
            algorithms.AES(self.key), modes.CBC(iv), backend=default_backend()
        )
        decryptor = cipher.decryptor()
        padded_data = (
            decryptor.update(encrypted_content) + decryptor.finalize()
        )

        # PKCS7 패딩 제거
        return self._unpad(padded_data).decode()

    def _pad(self, data: bytes) -> bytes:
        """
        PKCS7 패딩 처리
        """
        padding_length = 16 - (len(data) % 16)
        return data + bytes([padding_length] * padding_length)

    def _unpad(self, data: bytes) -> bytes:
        """
        PKCS7 패딩 제거
        """
        padding_length = data[-1]
        if padding_length < 1 or padding_length > 16:
            raise ValueError("Invalid padding.")
        return data[:-padding_length]
