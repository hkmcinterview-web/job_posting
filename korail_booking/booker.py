# -*- coding: utf-8 -*-
"""korail_booking — 개인용 코레일(KTX) 취소표 예약 도우미.

동작 방식:
  1) 본인 코레일 계정으로 로그인
  2) 설정한 구간/날짜/시간대의 열차에 빈자리가 있는지 여유 있는 간격으로 조회
  3) 빈자리가 뜨면 '예약'(좌석 확보)까지 자동 수행 — 결제는 하지 않음
  4) 예약 성공 시 텔레그램 + 폰 푸시로 즉시 알림
     → 코레일 규정상 예약 후 약 10~20분 내에 앱/웹에서 직접 결제하면 됩니다.

주의: 이 도구는 '본인 1인 개인 사용'을 전제로 합니다. 조회 간격을 사람이 하는
수준으로 유지하세요. 코레일 이용약관은 자동화 예매를 제한하며, 무리한 반복 조회는
계정 이용에 제한을 받을 수 있습니다.
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
from datetime import datetime, timedelta
from pathlib import Path

import yaml

from notifier import Notifier

try:
    from korail2 import (
        Korail,
        TrainType,
        ReserveOption,
        AdultPassenger,
        ChildPassenger,
        SoldOutError,
        NoResultsError,
        NeedToLoginError,
        KorailError,
    )
except ImportError:
    print("korail2 가 설치되어 있지 않습니다.  pip install -r requirements.txt", file=sys.stderr)
    raise

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("korail_booking")


def load_config(path: str) -> dict:
    p = Path(path)
    if not p.exists():
        log.error("설정 파일을 찾을 수 없습니다: %s  (config.example.yaml 을 복사해 만드세요)", path)
        sys.exit(1)
    return yaml.safe_load(p.read_text(encoding="utf-8"))


def resolve_train_types(names: list[str]) -> list:
    out = []
    for n in names or ["KTX"]:
        try:
            out.append(getattr(TrainType, n.strip().upper()))
        except AttributeError:
            log.warning("알 수 없는 train_type '%s' — 무시합니다.", n)
    return out or [TrainType.KTX]


def resolve_option(name: str):
    try:
        return getattr(ReserveOption, (name or "GENERAL_FIRST").strip().upper())
    except AttributeError:
        log.warning("알 수 없는 seat_option '%s' — GENERAL_FIRST 로 대체합니다.", name)
        return ReserveOption.GENERAL_FIRST


def build_passengers(trip: dict) -> list:
    passengers = []
    adults = int(trip.get("adults", 1) or 0)
    children = int(trip.get("children", 0) or 0)
    if adults > 0:
        passengers.append(AdultPassenger(adults))
    if children > 0:
        passengers.append(ChildPassenger(children))
    return passengers or [AdultPassenger(1)]


def in_time_window(train, time_to: str) -> bool:
    """time_to(HHMMSS) 이전 출발 열차만 통과. time_to 가 비면 항상 통과."""
    if not time_to:
        return True
    dep = getattr(train, "dep_time", None)
    if not dep:
        return True
    return str(dep) <= str(time_to)


def describe(train) -> str:
    return (
        f"{getattr(train, 'train_type_name', '열차')} "
        f"{getattr(train, 'train_no', '')} | "
        f"{getattr(train, 'dep_name', '')}({getattr(train, 'dep_time', '')[:4]}) → "
        f"{getattr(train, 'arr_name', '')}({getattr(train, 'arr_time', '')[:4]})"
    )


def run(config_path: str) -> None:
    cfg = load_config(config_path)
    trip = cfg["trip"]
    poll = cfg.get("polling", {})
    notifier = Notifier(cfg.get("notify", {}))

    train_types = resolve_train_types(trip.get("train_types"))
    option = resolve_option(trip.get("seat_option"))
    passengers = build_passengers(trip)
    time_to = str(trip.get("time_to") or "")

    interval = float(poll.get("interval_seconds", 40))
    jitter = float(poll.get("jitter_seconds", 15))
    stop_after = bool(poll.get("stop_after_reserve", True))
    max_minutes = float(poll.get("max_minutes", 0) or 0)

    korail = Korail(cfg["korail"]["login_id"], cfg["korail"]["password"], auto_login=False)
    if not korail.login():
        log.error("로그인 실패 — 회원번호/비밀번호를 확인하세요.")
        notifier.send("코레일 예약 도우미", "❌ 로그인 실패. 설정을 확인하세요.")
        sys.exit(1)
    log.info("로그인 성공. 조회 시작: %s → %s / %s %s 이후",
             trip["dep"], trip["arr"], trip["date"], trip["time_from"])
    notifier.send("코레일 예약 도우미", f"🔍 조회 시작\n{trip['dep']}→{trip['arr']} "
                                        f"{trip['date']} {trip['time_from']}~{time_to or '종일'}")

    deadline = datetime.now() + timedelta(minutes=max_minutes) if max_minutes > 0 else None
    attempt = 0

    while True:
        if deadline and datetime.now() > deadline:
            log.info("최대 실행 시간(%s분)에 도달하여 종료합니다.", max_minutes)
            notifier.send("코레일 예약 도우미", "⏱ 제한 시간 도달. 예약 없이 종료합니다.")
            break

        attempt += 1
        found_seat = False
        try:
            for tt in train_types:
                trains = korail.search_train_allday(
                    trip["dep"], trip["arr"], trip["date"], trip["time_from"],
                    train_type=tt, passengers=passengers, include_no_seats=True,
                )
                for train in trains:
                    if not in_time_window(train, time_to):
                        continue
                    if not train.has_seat():
                        continue

                    found_seat = True
                    log.info("빈자리 발견! %s — 예약 시도", describe(train))
                    try:
                        korail.reserve(train, passengers=passengers, option=option)
                    except SoldOutError:
                        log.info("예약 직전 매진 — 계속 조회합니다.")
                        continue

                    msg = (
                        f"✅ 예약 완료!\n{describe(train)}\n\n"
                        f"⏰ 약 10분 내에 코레일 앱/웹에서 결제하세요.\n"
                        f"(마이페이지 > 승차권 확인)"
                    )
                    log.info("예약 성공: %s", describe(train))
                    notifier.send("🚄 코레일 예약 완료", msg)

                    if stop_after:
                        log.info("예약 성공. 프로그램을 종료합니다. 잊지 말고 결제하세요!")
                        return

        except NeedToLoginError:
            log.warning("세션 만료 — 재로그인 시도")
            korail.login()
            continue
        except NoResultsError:
            pass  # 해당 조건 열차 없음 — 다음 주기에 다시 시도
        except KorailError as e:
            log.warning("코레일 오류: %s — 다음 주기에 재시도", e)
        except Exception as e:  # noqa: BLE001 — 어떤 오류든 루프를 멈추지 않도록
            log.warning("예상치 못한 오류: %s — 다음 주기에 재시도", e)

        wait = interval + random.uniform(0, jitter)
        if not found_seat:
            log.info("[%d회] 빈자리 없음. %.0f초 후 재조회", attempt, wait)
        time.sleep(wait)


def main() -> None:
    ap = argparse.ArgumentParser(description="개인용 코레일 취소표 예약 도우미")
    ap.add_argument("-c", "--config", default="config.yaml", help="설정 파일 경로 (기본: config.yaml)")
    args = ap.parse_args()
    try:
        run(args.config)
    except KeyboardInterrupt:
        log.info("사용자 중단(Ctrl+C). 종료합니다.")


if __name__ == "__main__":
    main()
