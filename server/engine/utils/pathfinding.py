# engine/utils/pathfinding.py
"""
Contains the A* pathfinding algorithm for navigation within the game world.
"""
import heapq
from typing import TYPE_CHECKING, List, Optional, Tuple

if TYPE_CHECKING:
    from engine.world.world import World

def find_path(world: 'World', source_region_id: str, source_room_id: str, target_region_id: str, target_room_id: str) -> Optional[List[str]]:
    """
    Finds the shortest path between two rooms using the A* algorithm.
    Returns a list of direction strings (e.g., ['north', 'east']) or None if no path exists.
    """
    start_node = (source_region_id, source_room_id)
    goal_node = (target_region_id, target_room_id)

    if start_node == goal_node:
        return []

    # Priority queue: (priority, (region_id, room_id))
    pq = [(0, start_node)]
    # g_score: cost from start to a node
    g_score = {start_node: 0}
    # cheapest_path_to: map of node to the path of directions to reach it
    cheapest_path_to = {start_node: []}

    while pq:
        _, current_node = heapq.heappop(pq)

        if current_node == goal_node:
            return cheapest_path_to[goal_node]

        current_region_id, current_room_id = current_node
        region = world.get_region(current_region_id)
        if not region:
            continue
        room = region.get_room(current_room_id)
        if not room:
            continue

        for direction, exit_id in room.exits.items():
            next_region_id, next_room_id = current_region_id, exit_id
            if ":" in exit_id:
                next_region_id, next_room_id = exit_id.split(":")

            next_node = (next_region_id, next_room_id)

            # Check if the destination room actually exists
            next_region = world.get_region(next_region_id)
            if not next_region or not next_region.get_room(next_room_id):
                continue

            new_cost = g_score[current_node] + 1
            if next_node not in g_score or new_cost < g_score[next_node]:
                g_score[next_node] = new_cost
                # Heuristic: Add a small penalty for changing regions to prefer intra-region paths
                priority = new_cost + (0 if next_region_id == target_region_id else 1)
                heapq.heappush(pq, (priority, next_node))
                cheapest_path_to[next_node] = cheapest_path_to[current_node] + [direction]

    return None # No path found