from typing import Any

from openai import OpenAI

from modules.llm.base_client import LLMClient


class OpenAIClient(LLMClient):
    """OpenAI를 위한 LLMClient 구현"""

    api_key: str
    _client: OpenAI

    @classmethod
    def get_client(cls, api_key: str) -> "OpenAI":
        return super().get_client(api_key)

    @classmethod
    def _initialize_client(cls, api_key: str) -> "OpenAI":
        """OpenAI 클라이언트 초기화"""
        cls.api_key = api_key
        return OpenAI(api_key=api_key)

    def generate_text(
        self,
        prompt: str,
        model: str = "gpt-4o",
        system_prompt: str = "",
        **kwargs: Any,
    ) -> str:
        """
        OpenAI 모델을 사용하여 텍스트 생성

        매개변수:
            prompt: 입력 프롬프트 (유저 메시지 내용)
            model: 사용할 모델(기본값: gpt-4o)
            system_prompt: 시스템 프롬프트 (선택적)
            **kwargs: OpenAI API를 위한 추가 매개변수

        반환값:
            생성된 텍스트
        """
        client = self._client
        if not client:
            raise ValueError("client 가 존재하지 않씁니다.")

        # 메시지 구성
        messages = []

        # 시스템 프롬프트가 있으면 추가
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        response = client.chat.completions.create(
            model=model, messages=messages, **kwargs
        )
        result: str = response.choices[0].message.content
        return result

    def generate_embedding(
        self, text: str | list[str], model: str = "text-embedding-3-large"
    ) -> list[float]:
        """
        OpenAI를 사용하여 텍스트 임베딩 생성

        매개변수:
            text: 입력 텍스트 또는 텍스트 목록
            model: 사용할 임베딩 모델

        반환값:
            벡터 임베딩
        """
        client = self._client
        if not client:
            raise ValueError("client 가 존재하지 않씁니다.")

        response = client.embeddings.create(model=model, input=text)
        result: list[float] = response.data[0].embedding
        return result
