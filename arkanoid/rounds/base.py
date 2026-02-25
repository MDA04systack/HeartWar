import collections
import pygame

from arkanoid.sprites.edge import (TopEdge,
                                   SideEdge)
from arkanoid.sprites.brick import BrickColour

# ───────────────────────────────────────────────
# 기본 배경 색상 정의
# 각 라운드 파일(round1.py 등)에서 이 상수들을 불러와서 사용
# 필요하다면 각 라운드별로 `_create_background()` 를 오버라이드해 # 이미지 배경을 적용 가능
BLUE = (0, 0, 128)
GREEN = (0, 128, 0)
RED = (128, 0, 0)
# ───────────────────────────────────────────────

class BaseRound:
    """
    Arkanoid의 '라운드(스테이지)'를 위한 기본 클래스.

    - 공, 패들, 벽돌, 배경 등 스테이지 공통 요소를 초기화
    - Round1, Round2 같은 실제 라운드는 이 클래스를 상속받아
      `_create_bricks()`, `_get_background_colour()` 등을 구체적으로 구현.
    - 경계(Edge), 벽돌 배치, 클리어 조건, 다음 라운드 연결 등의 기본 로직을 공통 제공.
    """
    def __init__(self, top_offset):
        """
           라운드 기본 설정 초기화.

        Args:
            top_offset (int):
                화면 상단에서 '게임 영역'이 얼마나 아래에서 시작할지를 픽셀 단위로 지정.
                (예: 점수판, 타이머 등을 위한 여백)
        """
        # ───────────────────────────────────────────────
        # 게임 영역 배치 관련 설정
        self.top_offset = top_offset
        self.screen = pygame.display.get_surface() # pygame의 전체 디스플레이 Surface (렌더링 대상)
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 라운드 이름 (화면 시작 시 표시)
        self.name = 'Round name not set!'
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 경계(벽) 스프라이트 생성
        # 왼쪽·오른쪽·위쪽 벽 객체를 만들고 위치시킴.
        # 반환값은 namedtuple로 (left, right, top) 접근 가능.
        self.edges = self._create_edges()
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 배경 Surface 생성
        # 기본은 단색 배경. (라운드마다 override 가능)
        self.background = self._create_background()
        
        # ─ 배경을 실제 화면에 그려두기 (상단 여백 고려)
        self.screen.blit(self.background, (0, top_offset))
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 벽돌 생성 및 배치
        # 각 라운드별 `_create_bricks()` 가 실제 구현해야 함.
        # (벽돌 그룹을 만들어 위치를 계산하고 배치)
        self.bricks = self._create_bricks()
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 난이도·속도 튜닝용 파라미터
        # 각 라운드에서 이 값을 오버라이드해 조정 가능.
        self.ball_base_speed_adjust = 0         # 공의 기본 속도 조절
        self.paddle_speed_adjust = 0            # 패들 이동 속도 조절
        self.ball_speed_normalisation_rate_adjust = 0 # 공 속도 정상화 비율 조절
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 적(Enemy) 관련 설정 (기본 None)
        self.enemy_type = None      # 출현 시킬 적 클래스
        self.num_enemies = 0        # 적 개수
        # ───────────────────────────────────────────────
        
        # ───────────────────────────────────────────────
        # 다음 라운드 연결 설정
        self.next_round = None
        # ───────────────────────────────────────────────

        # ───────────────────────────────────────────────
        # 벽돌 파괴 카운터
        # 라운드 완료 조건(모든 벽돌 파괴)에 사용.
        self._bricks_destroyed = 0
        # ───────────────────────────────────────────────

    # ──────────────────────────────────────────────────────────────────────
    # 라운드 완료 판정
    #  - 'gold' 벽돌은 파괴 불가/예외 취급인 경우가 많음 → 카운트에서 제외
    #  - 모든 파괴 가능한 벽돌을 부수면 True
    # ──────────────────────────────────────────────────────────────────────
    
    @property
    def complete(self):
        """Whether the rounds has been completed (all bricks destroyed).
        
        Returns:
            True if the round has been completed. False otherwise.
            #bool: True면 라운드 클리어.
        """
        # gold 벽돌은 카운트에서 제외한 총 벽돌 수
        return self._bricks_destroyed >= len([brick for brick in self.bricks
                                              if brick.colour !=
                                              BrickColour.gold])

    # 벽돌이 부서질 때 게임 쪽(예: Brick 스프라이트)에서 호출해주는 훅
    def brick_destroyed(self):
        """Conveys to the round that a brick has been destroyed in the game."""
        # 벽돌 1개가 파괴되었음을 라운드에 알림
        self._bricks_destroyed += 1

    # ─ 현재 라운드에서 적을 언제 풀어줄지(타이밍/조건)는 라운드별로 다름
    #   → 하위 클래스에서 구현
    def can_release_enemies(self):
        """Whether the enemies can be released into the game.

        This is round specific, so concrete round subclasses should implement
        this method.
        """
        # bool: 적을 투입해도 되는 타이밍이면 True.
        raise NotImplementedError('Subclasses must implement '
                                  'can_release_enemies()')

    # ──────────────────────────────────────────────────────────────────────
    # 편의 함수: '그리드 좌표'로 벽돌 배치하기
    #   - 실제 픽셀 좌표 계산을 숨겨주고,
    #     (x, y)를 '벽돌 한 칸' 단위의 격자 좌표로 간주
    #   - Edge 두께와 top_offset을 고려한 실제 화면 위치를 자동 계산
    # ──────────────────────────────────────────────────────────────────────
    def _blit_brick(self, brick, x, y):
        """Blits the specified brick onto the game area by using a
        relative coordinate for the position of the brick.

        This is a convenience method that concrete subclasses can use when
        setting up bricks. It assumes that the game area (area within the
        edges) is split into a grid where each grid square corresponds to one
        brick. The top left most brick is considered position (0, 0). This
        allows clients to avoid having to work with actual screen positions.

        Note that this method will modify the brick's rect attribute once
        the brick has been set.

        Args:
            brick:
                The brick instance to position on the grid.
            x:
                The x position on the grid.
            y:
                The y position on the grid.
            brick: 벽돌 스프라이트 인스턴스(이미 image/rect 보유)
            x (int): 그리드상의 X(0이 가장 왼쪽)
            y (int): 그리드상의 Y(0이 가장 위)

        Returns:
            The blitted brick.
        """
        # 그리드 한 칸은 '벽돌 이미지의 폭/높이' 크기
        offset_x = brick.rect.width * x
        offset_y = brick.rect.height * y

        # 화면상의 실제 배치 위치 계산:
        #  - 왼쪽은 left edge의 오른쪽 바깥
        #  - 위쪽은 top edge의 아래쪽 바깥
        rect = self.screen.blit(brick.image, (self.edges.left.rect.x +
                                self.edges.left.rect.width + offset_x,
                                self.edges.top.rect.y +
                                self.edges.top.rect.height + offset_y))
        brick.rect = rect   # 스프라이트의 충돌/렌더 기준 rect를 최신화
        return brick

    # ──────────────────────────────────────────────────────────────────────
    # 배경 Surface 생성(기본: 단색)
    #   - 더 리치한 배경(텍스처/이미지)로 바꾸려면 이 메서드를
    #     하위 클래스에서 '완전히' 오버라이드하면 됨.
    # ──────────────────────────────────────────────────────────────────────
    def _create_background(self):
        """Create the background surface for the round.

        This method provides a default implementation that simply creates a
        solid colour for the background, delegating to an abstract hook method
        for the colour itself. Subclasses may ovrerride this if they wish to
        provide a more elaborate background (e.g. textured) for a round.

        Returns:
            The background surface.
            pygame.Surface: 라운드 전용 배경 Surface
        """
        background = pygame.Surface(self.screen.get_size())
        background = background.convert()  # 디스플레이 포맷 맞추기(렌더 성능 ↑)
        background.fill(self._get_background_colour())
        return background

    # ─ 라운드별 배경색을 넘겨주는 추상 훅
    def _get_background_colour(self):
        """Abstract method to obtain the background method for a round.

        Subclasses must implement this to return the colour, or alternatively,
        override _create_background() completely to create a more elaborate
        background.

        Returns:
            The background colour.
        """
        raise NotImplementedError(
            'Subclasses must implement _get_background_colour()')
    
    # ──────────────────────────────────────────────────────────────────────
    # 게임 영역의 Edge(왼/오/위) 생성 및 위치 지정
    #   - 기본적으로 정적 Edge를 사용. 애니메이션 Edge가 필요하면 오버라이드
    #   - 반환값은 namedtuple('edge', 'left right top')
    # ──────────────────────────────────────────────────────────────────────
    def _create_edges(self):
        """Create the edge sprites and position them at the edges of the
        screen.

        This implementation creates static edges. Subclasses may override
        if they wish to provide some special animation within an edge.

        Returns:
            A named tuple with attributes 'left', 'right', and 'top' that
            reference the corresponding edge sprites.
        """
        edges = collections.namedtuple('edge', 'left right top')
        left_edge = SideEdge('left')
        right_edge = SideEdge('right')
        top_edge = TopEdge()
        
        # Edge의 실제 화면 위치 지정(상단 여백 포함)
        left_edge.rect.topleft = 0, self.top_offset
        right_edge.rect.topright = self.screen.get_width(), self.top_offset
        top_edge.rect.topleft = left_edge.rect.width, self.top_offset
        return edges(left_edge, right_edge, top_edge)

    # ──────────────────────────────────────────────────────────────────────
    # 벽돌 생성/배치 추상 훅
    #   - 각 라운드 파일(round1.py 등)에서 '반드시' 구현해야 함.
    #   - self._blit_brick()을 활용하면 격자 좌표 기반으로 간편 배치 가능.
    # ──────────────────────────────────────────────────────────────────────
    def _create_bricks(self):
        """Create the bricks and position them on the screen.

        Subclasses must override this abstract method to create and position
        the bricks.

        Returns:
            A pygame.sprite.Group of bricks.
        """
        raise NotImplementedError('Subclasses must implement _create_bricks()')