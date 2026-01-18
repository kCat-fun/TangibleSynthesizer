import domain.geometry.map_positions as map_positions
from infrastructure import *

class MoveTarget:
    @staticmethod
    async def move_target(cube: CubeController, x: int, y: int, _angle: int = None, speed: int = 20) -> dict:
        pos = (map_positions.maps)[y][x]
        print(pos)
        x_pos = pos['x']
        y_pos = pos['y']
        angle = pos['angle'] if _angle is None else _angle
        await cube.action.move_position(x_pos, y_pos, angle, speed)
