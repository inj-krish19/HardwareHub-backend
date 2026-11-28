"""Recognising error screens from the text of a photo. Pure tests, plus a check against the real guides."""
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.rule_engine import screen_text
from app.rule_engine.matcher import rank_matches

SEED = Path(__file__).resolve().parent.parent / "app" / "data" / "seed"

BSOD = """Your PC ran into a problem and needs to restart. We're just collecting some error info, and then we'll restart for you.
42% complete
For more information about this issue and possible fixes, visit https://www.windows.com/stopcode
If you call a support person, give them this info: Stop code: CRITICAL_PROCESS_DIED"""
BOOT = "Reboot and Select proper Boot device or Insert Boot Media in selected Boot device and press a key"
NO_SIGNAL = "HDMI 1\nNo Signal\nCheck signal cable"
FAN = "CPU Fan Error!\nPress F1 to Run SETUP"
HOT = "Warning: CPU over temperature. System will shut down in 10 seconds."
MEM = "Windows Memory Diagnostic: memory test failed. Errors were detected."


def _guides():
    out = []
    for file in sorted(SEED.glob("*_symptoms.json")):
        for e in json.loads(file.read_text(encoding="utf-8")):
            out.append(SimpleNamespace(id=e["title"], title=e["title"], category=e["category"], bot_type=e.get("bot_type", "diagnostic"),
                                       keywords=", ".join(e.get("keywords", []))))
    return out


@pytest.mark.parametrize(
    "text,kind",
    [(BSOD, "bsod"), (BOOT, "boot_device"), (NO_SIGNAL, "no_signal"), (FAN, "fan_error"), (HOT, "overheating"), (MEM, "memory_error")],
)
def test_each_kind_of_screen_is_recognised(text, kind):
    assert kind in [h.kind for h in screen_text.detect(text)]


def test_recognition_ignores_case_punctuation_and_ocr_line_breaks():
    assert [h.kind for h in screen_text.detect("NO   BOOTABLE\nDEVICE !!")] == ["boot_device"]
    assert [h.kind for h in screen_text.detect("your pc RAN into a problem")] == ["bsod"]


def test_ordinary_text_is_not_a_screen():
    for text in ("my pc is slow", "how do i clean my pc", "ram not detected", "", "   "):
        assert screen_text.detect(text) == []


def test_two_screens_in_one_photo_are_both_found_in_order():
    kinds = [h.kind for h in screen_text.detect("CPU Fan Error! ... then later: no signal")]
    assert kinds == ["fan_error", "no_signal"]


def test_augment_and_describe():
    hints = screen_text.detect(NO_SIGNAL)
    assert screen_text.augment_query("HDMI No Signal", hints).startswith("HDMI No Signal ")
    assert "monitor no signal" in screen_text.augment_query("x", hints)
    assert screen_text.augment_query("plain", []) == "plain"
    assert screen_text.describe(hints) == "That looks like a 'no signal' message from the monitor."
    assert screen_text.describe([]) == ""
    assert screen_text.describe(screen_text.detect(BSOD + " " + MEM)).count(" and ") == 1


# ---- the point of it all: the right real guide is suggested ----

@pytest.mark.parametrize(
    "text,expected",
    [
        (BSOD, "Random crashes or Blue Screen errors"),
        (NO_SIGNAL, "Monitor says no signal"),
        (FAN, "Cooler not detected or fan/pump headers not reading"),
        (HOT, "Computer shuts down by itself because of heat"),
        (MEM, "Random crashes or Blue Screen errors"),
    ],
)
def test_the_screen_text_finds_the_right_guide_among_the_real_ones(text, expected):
    guides = _guides()
    hints = screen_text.detect(text)
    top3 = [g.title.strip() for g in rank_matches(screen_text.augment_query(text, hints), guides, None, limit=3)]
    assert expected in top3, top3


def test_the_hint_makes_the_blue_screen_suggestion_precise():
    # The words on a blue screen already find the guide, but with noise: two unrelated guides come along.
    # The hint leaves only the right one.
    guides = _guides()
    plain = [g.title.strip() for g in rank_matches(BSOD, guides, None, limit=3)]
    helped = [g.title.strip() for g in rank_matches(screen_text.augment_query(BSOD, screen_text.detect(BSOD)), guides, None, limit=3)]
    assert helped == ["Random crashes or Blue Screen errors"]
    assert len(plain) > len(helped)


def test_the_boot_drive_hint_reaches_the_storage_guide():
    # The storage guides are not in the seed folder yet. Use the real one as soon as it is there;
    # until then a stand-in with realistic keywords proves the wiring (not the live ranking).
    guides = _guides()
    real = [g for g in guides if g.title.strip() == "Storage drive not detected"]
    stand_in = SimpleNamespace(id="s", title="Storage drive not detected", category="Storage", bot_type="diagnostic",
                               keywords="storage drive not detected, drive not detected, boot drive not found, ssd not showing up")
    pool = guides if real else [stand_in, *guides]
    top = rank_matches(screen_text.augment_query(BOOT, screen_text.detect(BOOT)), pool, None, limit=3)
    assert top and top[0].title.strip() == "Storage drive not detected"


# ---- part labels ----

RAM_LABEL = "Corsair Vengeance LPX 16GB (2x8GB) DDR4 3200MHz CL16 1.35V"
SSD_LABEL = "Samsung 970 EVO Plus NVMe M.2 SSD 500GB PCIe Gen3"
GPU_LABEL = "GIGABYTE GeForce RTX 3060 12GB GAMING OC"
CPU_LABEL = "AMD Ryzen 5 5600 6-Core Processor 3.5GHz"
PSU_LABEL = "Corsair CV550 550W 80 PLUS Bronze ATX12V Power Supply"


@pytest.mark.parametrize(
    "text,kind,label",
    [
        (RAM_LABEL, "part_ram", "a DDR4 3200 MHz memory module (16GB)"),
        (SSD_LABEL, "part_storage", "an NVMe / M.2 SSD"),
        (GPU_LABEL, "part_gpu", "a graphics card (RTX 3060)"),
        (CPU_LABEL, "part_cpu", "a processor (Ryzen 5 5600)"),
        (PSU_LABEL, "part_psu", "a power supply (550W)"),
    ],
)
def test_part_labels_are_read_and_described_from_what_is_printed(text, kind, label):
    hints = screen_text.detect(text)
    assert [h.kind for h in hints] == [kind]
    assert hints[0].label == label


def test_a_label_with_less_printed_on_it_gets_a_plainer_description():
    assert screen_text.detect("DDR5")[0].label == "a DDR5 memory module"
    assert screen_text.detect("WD Blue 1TB SATA III 6Gb/s")[0].label == "a SATA drive"
    assert screen_text.detect("ASUS Radeon graphics")[0].label == "a graphics card"
    assert screen_text.detect("ATX12V power supply")[0].label == "a power supply"


@pytest.mark.parametrize(
    "text,expected",
    [
        (RAM_LABEL, "Will this RAM work with my motherboard?"),
        (SSD_LABEL, "Will this SSD work in my PC?"),
        (GPU_LABEL, "Will this graphics card fit and run in my PC?"),
        (CPU_LABEL, "Will this processor work with my motherboard?"),
        (PSU_LABEL, "Is my power supply strong enough for my parts?"),
    ],
)
def test_each_part_label_reaches_its_compatibility_guide(text, expected):
    top3 = [g.title.strip() for g in rank_matches(screen_text.augment_query(text, screen_text.detect(text)), _guides(), None, limit=3)]
    assert top3[0] == expected, top3


def test_a_screen_and_a_part_in_one_photo_are_both_reported():
    hints = screen_text.detect("DDR4 3200MHz   Memory test failed")
    assert {h.kind for h in hints} == {"part_ram", "memory_error"}