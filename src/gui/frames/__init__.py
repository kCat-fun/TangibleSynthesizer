"""GUI frames package"""
from .mode_select_frame import ModeSelectFrame
from .loop_sequencer_frame import LoopSequencerFrame
from .duet_frame import DuetFrame
from .debug_frame import DebugFrame
from .playback_frame import PlaybackFrame

__all__ = [
    'ModeSelectFrame', 'LoopSequencerFrame', 'DuetFrame',
    'DebugFrame', 'PlaybackFrame'
]
