"""Vietnamese business-rule error messages.

Mirrors the resolved strings from the frontend i18n (``src/i18n/locales/vi.json``)
and ``src/utils/constants/errors.ts`` so error copy stays identical to what the
client previously produced locally.
"""


class BusinessError(Exception):
    """Raised on a business-rule violation; surfaced as HTTP 400 with a vi message."""

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


# Match
MATCH_NAME_REQUIRED = "Vui lòng nhập tên trận đấu"
MATCH_NOT_FOUND = "Không tìm thấy trận đấu"
MATCH_ID_INVALID = "ID trận đấu không hợp lệ"
MATCH_MIN_PLAYERS = "Trận đấu cần ít nhất 2 người chơi"

# Player
PLAYER_NAME_REQUIRED = "Vui lòng nhập tên người chơi"
PLAYER_NOT_FOUND = "Không tìm thấy người chơi"
PLAYER_ID_INVALID = "ID người chơi không hợp lệ"
PLAYER_NAME_EXISTS = "Tên người chơi đã tồn tại"

# Game
GAME_NUMBER_INVALID = "Ván đấu không hợp lệ"
GAME_SCORE_INVALID = "Điểm số không hợp lệ"
GAME_CURRENT_SCORE_NOT_ZERO = "Tổng số điểm của ván đấu hiện tại không bằng 0"

# Admin
ADMIN_INVALID_CREDENTIALS = "Sai tên đăng nhập hoặc mật khẩu"


def player_name_exists(name: str) -> str:
    return f"Tên người chơi {name} đã tồn tại"


def game_score_not_zero(game_number: int) -> str:
    return f"Tổng số điểm của ván đấu {game_number} không bằng 0"
