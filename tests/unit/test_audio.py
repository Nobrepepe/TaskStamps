from pathlib import Path

from task_stamps.utilities.audio import AudioPlayer


def test_play_sequence_waits_for_each_sound_in_order(tmp_path, monkeypatch):
    global_sound = tmp_path / "global.wav"
    assigned_sound = tmp_path / "assigned.wav"
    global_sound.touch()
    assigned_sound.touch()

    player = AudioPlayer()
    player._player = "aplay"
    commands: list[list[str]] = []

    class ImmediateThread:
        def __init__(self, target, args, daemon):
            self.target = target
            self.args = args

        def start(self):
            self.target(*self.args)

    monkeypatch.setattr("task_stamps.utilities.audio.threading.Thread", ImmediateThread)
    monkeypatch.setattr(
        "task_stamps.utilities.audio.subprocess.run",
        lambda command, **_: commands.append(command),
    )

    assert player.play_sequence([global_sound, assigned_sound])
    assert commands == [
        ["aplay", str(global_sound)],
        ["aplay", str(assigned_sound)],
    ]


def test_play_sequence_ignores_missing_files(tmp_path, monkeypatch):
    player = AudioPlayer()
    player._player = "aplay"
    monkeypatch.setattr(
        "task_stamps.utilities.audio.threading.Thread",
        lambda **_: (_ for _ in ()).throw(AssertionError("thread should not start")),
    )

    assert not player.play_sequence([Path(tmp_path / "missing.wav")])
