import random
import pygame

from arkanoid.rounds.base import (BaseRound,
                                  RED, BLUE)     # 바꿔야함
from arkanoid.rounds.round2 import Round2
from arkanoid.sprites.brick import (Brick,
                                    BrickColour)
from arkanoid.sprites.enemy import EnemyType
from arkanoid.sprites.powerup import (ExpandPowerUp,
                                      ExtraLifePowerUp,
                                      SpeedPowerUp,
                                      SlowBallPowerUp,
                                      ReducePowerUp,
                                       DuplicatePowerUp)  # 수정함 duplicate


class Round1(BaseRound):
    """Round 1을 담당하는 클래스.
    
    - 라운드 1의 이름, 적(enemy) 종류, 적의 개수, 다음 라운드 정보를 설정한다.
    - BaseRound가 정의한 배경/벽/브릭 기본 구조 위에 라운드1만의 정보만 추가한다.
    """

    def __init__(self, top_offset):
        """round 1 초기화 함수.

        Args:
            top_offset(int):
                화면 맨 위에서부터 라운드(벽돌/벽/배경)를 얼마나 아래로 내려서 표시할지 결정하는 값.
                상단 HUD(점수, 하이스코어, 타이머 같은 UI)를 위해 일정 공간을 비워놓기 위한 offset.
        """
        # BaseRound 초기화 실행
        # BaseRound에서:
        # - 벽(Walls) 생성
        # - 기본 배경 Surface 생성
        # - 벽돌(Bricks) 배열 로딩
        # - 충돌 처리 기본 틀 설정
        super().__init__(top_offset)

         # HUD 등에 표시될 라운드 이름
        self.name = 'Round 1'
        # 다음 라운드로 어떤 클래스를 사용할지 지정
        # 라운드 클리어 시: self.next_round(top_offset) 형태로 새로운 라운드 객체 생성
        self.next_round = Round2
        # 라운드에서 등장할 적(enemy)의 종류 설정
        # EnemyType.cone 은 '콘 모양의 적' 패턴을 의미 (이미지 및 동작은 EnemyType 열거형에 정의)
        self.enemy_type = EnemyType.cone
        # 이 라운드에서 동시에 등장할 적(enemy) 수
        # round.enemies 리스트와 Enemy 스폰 규칙에 따라 관리됨
        self.num_enemies = 8

    def can_release_enemies(self):
        """Release the enemies when 25% of the bricks have been destroyed."""
        #len(self.bricks) // 4 → 전체 벽돌 개수를 4로 나눈 값 ex:80개면 80 // 4 = 20개 깨면 등장
        return self._bricks_destroyed >= len(self.bricks) // 4

    def _get_background_colour(self):
        return RED
    # def _create_background(self):
    #     bg = pygame.image.load("D:\\python\\arkanoid-master\\arkanoid\\data\\graphics\\unnamed.jpg").convert()
    #     return bg # 배경 바꾸려면 이 코드 사용하면 된다
        
    def _create_bricks(self):
        """벽돌을 생성하고 화면에 배치하여 sprite 그룹으로 반환한다.

        Returns:
            pygame.sprite.Group: 생성된 모든 벽돌 객체 그룹.
        """
          # 벽돌 5줄의 색상(레이어) 정의 -----
        colours = (BrickColour.silver, BrickColour.red, BrickColour.yellow,
                   BrickColour.blue, BrickColour.green)

        # Create the distribution of powerup classes.
        powerup_classes = []
        powerup_classes.extend([ReducePowerUp] * 6)     # 패들 줄어들기
        powerup_classes.extend([ExpandPowerUp] * 4)     # 패들 확장
        powerup_classes.extend([ExtraLifePowerUp] * 3)  # 생명 추가
        powerup_classes.extend([SlowBallPowerUp] * 2)   # 공 느려지기
        powerup_classes.extend([SpeedPowerUp] * 6)      # 공 빨리지기
        powerup_classes.extend([DuplicatePowerUp] * 2)  # 공 복제
        # 파워업 드랍 테이블을 랜덤으로 섞기
        random.shuffle(powerup_classes)

        # 벽돌 전체 65개 0~64
        # 어떤 벽돌이 파워업을 가질지 인덱스 선택
        # 0~51(52개) 중에서 (전체 파워업 수 - 4)개를 먼저 선택
        powerup_indexes = random.sample(range(52), len(powerup_classes) - 4)
        # 마지막 줄(52~64)에서 4개는 반드시 파워업 포함
        powerup_indexes += random.sample(range(52, 65), 4)
        #정렬하여 brick 생성 순서와 일치시키기
        powerup_indexes.sort()

        # 벽돌 생성
        bricks, count = [], 0

        # colours의 각 색상마다 12개 벽돌 → 총 60개(5줄 × 12)
        for colour in colours:
            for _ in range(12):
                # 기본적으로 파워업 없음
                powerup_class = None

                # 만약 현재 brick index가 powerup_indexes 안에 있다면
                # 하나 꺼내서 파워업 부여
                if count in powerup_indexes:
                    powerup_class = powerup_classes.pop(0)

                # Brick 생성 (hp=1, 색상=colour, 파워업=powerup_class)
                brick = Brick(colour, 1, powerup_cls=powerup_class)

                bricks.append(brick)
                count += 1
        # 벽돌을 실제 화면 위치에 배치
        self._position_bricks(bricks)

        return pygame.sprite.Group(*bricks)

    def _position_bricks(self, bricks):
        x, y, last_colour = 0, 3, None

        for brick in bricks:
            if brick.colour != last_colour:
                last_colour = brick.colour
                x = 0
                y += 1
            else:
                x += 1
            self._blit_brick(brick, x, y)
