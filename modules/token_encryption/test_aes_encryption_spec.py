import os
import unittest
from base64 import b64decode

from .aes_encryption import AESEncryption


class TestAESEncryption(unittest.TestCase):
    def setUp(self):
        # 32바이트 길이의 키를 생성
        self.valid_key = os.urandom(32)
        self.invalid_key = os.urandom(16)  # 16바이트 키 (유효하지 않음)
        self.aes = AESEncryption(self.valid_key)
        self.sample_text = "This is a test message for AES encryption!"

    def test_encrypt_decrypt(self):
        """암호화 후 복호화 결과가 원본과 동일한지 테스트"""
        encrypted = self.aes.encrypt(self.sample_text)
        decrypted = self.aes.decrypt(encrypted)
        self.assertEqual(
            self.sample_text, decrypted, "복호화 결과가 원본과 다릅니다."
        )

    def test_invalid_key_length(self):
        """키 길이가 잘못된 경우 ValueError 발생 확인"""
        with self.assertRaises(ValueError):
            AESEncryption(self.invalid_key)

    def test_encrypt_output_format(self):
        """암호화 결과가 base64로 인코딩된 문자열인지 테스트"""
        encrypted = self.aes.encrypt(self.sample_text)
        try:
            b64decode(encrypted)  # base64로 디코딩 가능해야 함
        except Exception:
            self.fail("암호화 결과가 base64로 인코딩되지 않았습니다.")

    def test_encrypt_different_iv(self):
        """같은 데이터를 여러 번 암호화해도 결과가 다른지 테스트 (IV 확인)"""
        encrypted1 = self.aes.encrypt(self.sample_text)
        encrypted2 = self.aes.encrypt(self.sample_text)
        self.assertNotEqual(
            encrypted1,
            encrypted2,
            "암호화 결과가 동일합니다. IV가 고정된 것 같습니다.",
        )

    def test_padding_unpadding(self):
        """PKCS7 패딩과 언패딩 테스트"""
        data = b"test"  # 4바이트 데이터
        padded = self.aes._pad(data)
        unpadded = self.aes._unpad(padded)
        self.assertEqual(data, unpadded, "패딩/언패딩 결과가 원본과 다릅니다.")

    def test_invalid_padding(self):
        """잘못된 패딩 데이터를 언패딩할 때 ValueError 발생 확인"""
        with self.assertRaises(ValueError):
            self.aes._unpad(b"invalid_padding")

    def test_empty_string(self):
        """빈 문자열 암호화 및 복호화 테스트"""
        encrypted = self.aes.encrypt("")
        decrypted = self.aes.decrypt(encrypted)
        self.assertEqual(
            "", decrypted, "빈 문자열 복호화 결과가 원본과 다릅니다."
        )

    def test_large_input(self):
        """큰 입력 데이터의 암호화 및 복호화 테스트"""
        large_text = "A" * 10_000  # 10,000자 문자열
        encrypted = self.aes.encrypt(large_text)
        decrypted = self.aes.decrypt(encrypted)
        self.assertEqual(
            large_text, decrypted, "큰 데이터 복호화 결과가 원본과 다릅니다."
        )

    def test_unicode_support(self):
        """유니코드 문자열 암호화 및 복호화 테스트"""
        unicode_text = "안녕하세요! AES 암호화 테스트입니다. 🚀"
        encrypted = self.aes.encrypt(unicode_text)
        decrypted = self.aes.decrypt(encrypted)
        self.assertEqual(
            unicode_text,
            decrypted,
            "유니코드 문자열 복호화 결과가 원본과 다릅니다.",
        )

    def test_invalid_encrypted_data(self):
        """잘못된 암호화 데이터 복호화 시 ValueError 발생 확인"""
        invalid_data = "invalid_encrypted_data"
        with self.assertRaises(ValueError):
            self.aes.decrypt(invalid_data)

    def test_corrupted_encrypted_data(self):
        """암호화된 데이터가 손상된 경우 복호화 오류 확인"""
        encrypted = self.aes.encrypt(self.sample_text)
        corrupted_data = encrypted[:-4] + "abcd"  # 암호화 데이터 끝부분을 손상

        with self.assertRaises(ValueError):
            self.aes.decrypt(corrupted_data)


if __name__ == "__main__":
    unittest.main(verbosity=2)
