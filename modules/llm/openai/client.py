import logging
from typing import TYPE_CHECKING, Any

from openai import (
    APIConnectionError,
    APIError,
    OpenAI,
)
from openai import (
    AuthenticationError as OpenAIAuthError,
)
from openai.types.chat import ChatCompletion
from openai.types.create_embedding_response import CreateEmbeddingResponse

from modules.llm.base_client import LLMClient
from modules.llm.exceptions import (
    AuthenticationError,
    ClientNotInitializedError,
    ConnectionError,
    GenerationError,
)

logger = logging.getLogger(__name__)


class OpenAIClient(LLMClient[OpenAI]):
    """OpenAI를 위한 LLMClient 구현"""

    # 클래스 변수
    if TYPE_CHECKING:
        # 타입 체커만 확인하는 코드 (IDE level 이라고 보면 됨)
        _instance: "OpenAIClient" | None = None
    else:
        # 런타임에 실행되는 코드
        _instance = None

    _client: OpenAI | None = None

    def __init__(self, client: OpenAI):
        """
        생성자는 private으로 취급됩니다. get_client() 클래스 메서드를 사용하세요.

        Args:
            client: 초기화된 OpenAI 클라이언트
        """
        self._client = client

    @classmethod
    def get_client(cls, api_key: str) -> "OpenAIClient":
        """
        LLM 클라이언트를 가져오거나 초기화합니다.
        싱글턴 패턴을 구현하여 하나의 인스턴스만 생성합니다.

        Args:
            api_key: OpenAI API 키 (필수)

        Returns:
            초기화된 OpenAIClient 인스턴스

        Raises:
            ValueError: API 키가 비어있는 경우
            AuthenticationError: API 키가 유효하지 않은 경우
            ConnectionError: OpenAI 서비스 연결에 실패한 경우
        """
        if not api_key:
            raise ValueError("API 키가 필요합니다.")

        if cls._instance is None:
            try:
                client = cls._initialize_client(api_key)
                cls._instance = cls(client)
            except OpenAIAuthError as e:
                logger.error(f"OpenAI 인증 실패: {str(e)}")
                raise AuthenticationError(
                    f"OpenAI API 키 인증 실패: {str(e)}"
                ) from e
            except APIConnectionError as e:
                logger.error(f"OpenAI 연결 실패: {str(e)}")
                raise ConnectionError(
                    f"OpenAI 서비스 연결 실패: {str(e)}"
                ) from e
            except Exception as e:
                logger.error(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
                raise ConnectionError(
                    f"OpenAI 클라이언트 초기화 실패: {str(e)}"
                ) from e

        return cls._instance

    @classmethod
    def _initialize_client(cls, api_key: str) -> OpenAI:
        """
        OpenAI 클라이언트 초기화

        Args:
            api_key: OpenAI API 키

        Returns:
            초기화된 OpenAI 클라이언트

        Raises:
            AuthenticationError: API 키가 유효하지 않은 경우
            ConnectionError: 서비스 연결에 실패한 경우
        """
        try:
            client = OpenAI(api_key=api_key)
            # API 키 검증을 위한 간단한 호출
            client.models.list()
            return client
        except OpenAIAuthError as e:
            logger.error(f"OpenAI 인증 실패: {str(e)}")
            raise AuthenticationError(
                f"OpenAI API 키 인증 실패: {str(e)}"
            ) from e
        except APIConnectionError as e:
            logger.error(f"OpenAI 연결 실패: {str(e)}")
            raise ConnectionError(f"OpenAI 서비스 연결 실패: {str(e)}") from e
        except Exception as e:
            logger.error(f"OpenAI 클라이언트 초기화 실패: {str(e)}")
            raise ConnectionError(
                f"OpenAI 클라이언트 초기화 실패: {str(e)}"
            ) from e

    def generate_text(
        self,
        prompt: str,
        system_prompt: str = "당신은 친절한 만능해결사 입니다. 사용자가 요청하는 모든 것을 처리해주세요",
        model: str = "gpt-4o-mini",
        **kwargs: Any,
    ) -> str:
        """
        OpenAI 모델을 사용하여 텍스트 생성

        Args:
            prompt: 입력 프롬프트 (유저 메시지 내용)
            system_prompt: 시스템 프롬프트 (선택적)
            model: 사용할 모델(기본값: gpt-4o)
            **kwargs: OpenAI API를 위한 추가 매개변수

        Returns:
            생성된 텍스트

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 입력이 유효하지 않은 경우
            ConnectionError: API 연결 실패
            AuthenticationError: 인증 실패
            GenerationError: 텍스트 생성 과정에서 오류 발생
        """
        if not self._client:
            raise ClientNotInitializedError(
                "클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )

        if not prompt:
            raise ValueError("프롬프트가 비어있습니다.")

        # 메시지 구성
        messages = []

        # 시스템 프롬프트가 있으면 추가
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})

        messages.append({"role": "user", "content": prompt})

        try:
            response: ChatCompletion = self._client.chat.completions.create(
                model=model,
                messages=messages,
                **kwargs,
            )

            if not response.choices or len(response.choices) == 0:
                raise GenerationError("응답에 선택 항목이 없습니다.")

            result = response.choices[0].message.content

            if result is None:
                return ""

            return str(result)

        except OpenAIAuthError as e:
            logger.error(f"OpenAI 인증 실패: {str(e)}")
            raise AuthenticationError(
                f"OpenAI API 키 인증 실패: {str(e)}"
            ) from e
        except APIConnectionError as e:
            logger.error(f"OpenAI 연결 실패: {str(e)}")
            raise ConnectionError(f"OpenAI 서비스 연결 실패: {str(e)}") from e
        except APIError as e:
            logger.error(f"OpenAI API 오류: {str(e)}")
            raise GenerationError(f"OpenAI API 오류: {str(e)}") from e
        except Exception as e:
            logger.error(f"텍스트 생성 실패: {str(e)}")
            raise GenerationError(f"텍스트 생성 실패: {str(e)}") from e

    def generate_embedding(
        self, text: str | list[str], model: str = "text-embedding-3-large"
    ) -> list[float] | list[list[float]]:
        """
        OpenAI를 사용하여 텍스트 임베딩 생성

        Args:
            text: 입력 텍스트 또는 텍스트 목록
            model: 사용할 임베딩 모델

        Returns:
            단일 텍스트 입력의 경우: 벡터 임베딩 리스트 (list[float])
            다중 텍스트 입력의 경우: 벡터 임베딩 리스트의 리스트 (list[list[float]])

        Raises:
            ClientNotInitializedError: 클라이언트가 초기화되지 않은 경우
            ValueError: 입력이 유효하지 않은 경우
            ConnectionError: API 연결 실패
            AuthenticationError: 인증 실패
            GenerationError: 임베딩 생성 과정에서 오류 발생
        """
        if not self._client:
            raise ClientNotInitializedError(
                "클라이언트가 초기화되지 않았습니다. get_client()를 먼저 호출하세요."
            )

        if not text:
            raise ValueError("임베딩을 위한 텍스트가 비어있습니다.")

        try:
            response: CreateEmbeddingResponse = self._client.embeddings.create(
                model=model, input=text
            )

            if not response.data or len(response.data) == 0:
                raise GenerationError("응답에 임베딩 데이터가 없습니다.")

            # 입력이 단일 문자열인 경우 단일 임베딩만 반환
            if isinstance(text, str):
                result: list[float] = response.data[0].embedding
                return result

            # 입력이 리스트인 경우 모든 임베딩 반환
            # response.data의 길이가 text의 길이와 일치하는지 확인
            if len(response.data) != len(text):
                logging.warning(
                    f"입력 텍스트 개수({len(text)})와 반환된 임베딩 개수({len(response.data)})가 일치하지 않습니다."
                )

            # 모든 임베딩을 리스트로 반환
            result = list()
            for data in response.data:
                temp = data.embedding
                result.append(temp)
            return result

        except OpenAIAuthError as e:
            logging.error(f"OpenAI 인증 실패: {str(e)}")
            raise AuthenticationError(
                f"OpenAI API 키 인증 실패: {str(e)}"
            ) from e
        except APIConnectionError as e:
            logging.error(f"OpenAI 연결 실패: {str(e)}")
            raise ConnectionError(f"OpenAI 서비스 연결 실패: {str(e)}") from e
        except APIError as e:
            logging.error(f"OpenAI API 오류: {str(e)}")
            raise GenerationError(f"OpenAI API 오류: {str(e)}") from e
        except Exception as e:
            logging.error(f"임베딩 생성 실패: {str(e)}")
            raise GenerationError(f"임베딩 생성 실패: {str(e)}") from e

    @classmethod
    def reset_client(cls) -> None:
        """
        클라이언트 인스턴스를 재설정합니다(테스트나 설정 변경 시 사용하기 위함)
        """
        cls._instance = None
