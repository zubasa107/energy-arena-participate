"""Offline regressions for the starter's DST payloads and source-day windows."""

from datetime import date, timedelta
import unittest
from unittest.mock import Mock, patch

import pandas as pd

import _starter_core as core


CASES = [
    (date(2026, 3, 28), "normal", "2026-03-27T23:00:00Z", "2026-03-28T23:00:00Z"),
    (date(2026, 3, 29), "spring", "2026-03-28T23:00:00Z", "2026-03-29T22:00:00Z"),
    (date(2026, 3, 30), "after_spring", "2026-03-29T22:00:00Z", "2026-03-30T22:00:00Z"),
    (date(2026, 10, 25), "autumn", "2026-10-24T22:00:00Z", "2026-10-25T23:00:00Z"),
    (
        date(2026, 10, 26),
        "after_autumn",
        "2026-10-25T23:00:00Z",
        "2026-10-26T23:00:00Z",
    ),
]


def source_series(day, minutes=15, base=0):
    # Local date bounds are independent of the implementation under test.
    index = pd.date_range(
        pd.Timestamp(day, tz="Europe/Berlin"),
        pd.Timestamp(day + timedelta(days=1), tz="Europe/Berlin"),
        freq=f"{minutes}min",
        inclusive="left",
    ).tz_convert("UTC")
    return pd.Series([float(base + i) for i in range(len(index))], index=index)


def context(minutes=15, objective="point"):
    return core.ChallengeContext(
        challenge_id="2",
        challenge_name="DE-LU prices",
        target_code="day_ahead_price",
        target_name="Day-Ahead Prices",
        area="DE_LU",
        areas=["DE_LU"],
        forecast_objective=objective,
        accepted_forecast_format=objective,
        reference_timezone="Europe/Berlin",
        target_period_timezone="Europe/Berlin",
        target_period_type="calendar_day",
        probabilistic_quantiles=[0.1, 0.5, 0.9],
        max_ensemble_size=3,
        smard_counterpart=core.SmardCounterpartSpec(
            module_id=1,
            region="DE",
            resolution={15: "quarterhour", 30: "halfhour", 60: "hour"}[minutes],
            source_unit="EUR/MWh",
            target_unit="EUR/MWh",
            value_multiplier=1.0,
        ),
        baseline_supported=True,
        challenge_detail={},
    )


def expected_values(kind, minutes, base=0):
    slots = 60 // minutes
    hours = 23 if kind == "after_spring" else 25 if kind == "after_autumn" else 24
    values = [float(base + i) for i in range(hours * slots)]
    if kind == "spring":
        return values[: 2 * slots] + values[3 * slots :]
    if kind == "autumn":
        return values[: 3 * slots] + values[2 * slots : 3 * slots] + values[3 * slots :]
    if kind == "after_spring":
        return values[: 2 * slots] + values[2 * slots : 3 * slots] + values[2 * slots :]
    if kind == "after_autumn":
        return values[: 3 * slots] + values[4 * slots :]
    return values


class StarterDstTests(unittest.TestCase):
    def test_point_quantile_and_ensemble_payloads_across_dst(self):
        # 90 cases: both providers, three resolutions, five day shapes,
        # and all objectives. A distinct history value exposes bad sample
        # alignment rather than accidentally passing through the point fallback.
        config = {
            **core.TARGET_BASELINES["day_ahead_price"],
            "history_start_lookback_days": 7,
            "history_step_days": 7,
            "history_count": 1,
        }
        for target, kind, start, end in CASES:
            for minutes in (15, 30, 60):
                for provider in ("smard", "entsoe"):
                    for objective in ("point", "quantile", "ensemble"):
                        with self.subTest(
                            target=target,
                            minutes=minutes,
                            provider=provider,
                            objective=objective,
                        ):

                            def fetch(*, delivery_date, **kwargs):
                                base = (
                                    0
                                    if delivery_date == target - timedelta(days=1)
                                    else 1000
                                )
                                # Providers/custom loaders may return unsorted data.
                                series = source_series(delivery_date, minutes, base)
                                if provider == "entsoe":
                                    series = series.tz_convert("Europe/Berlin")
                                return series.iloc[::-1]

                            with (
                                patch.dict(
                                    core.TARGET_BASELINES, {"day_ahead_price": config}
                                ),
                                patch.object(
                                    core, "_fetch_source_series", side_effect=fetch
                                ),
                            ):
                                payload = core.build_payload_from_source(
                                    target_date=target,
                                    context=context(minutes, objective),
                                    data_source=provider,
                                    entsoe_api_key="unused",
                                )
                            point_values = expected_values(kind, minutes)
                            history_kind = (
                                kind if kind in ("spring", "autumn") else "normal"
                            )
                            history_values = expected_values(
                                history_kind, minutes, base=1000
                            )
                            expected = (
                                point_values
                                if objective == "point"
                                else [[v] * 3 for v in history_values]
                            )
                            self.assertEqual(payload["values"], expected)
                            self.assertEqual(payload["challenge_id"], "2")
                            self.assertNotIn("area", payload)
                            self.assertEqual(
                                payload["target_start"],
                                pd.Timestamp(target, tz="Europe/Berlin").isoformat(),
                            )
                            self.assertEqual(
                                len(payload["values"]),
                                len(
                                    pd.date_range(
                                        start,
                                        end,
                                        freq=f"{minutes}min",
                                        inclusive="left",
                                    )
                                ),
                            )

    def test_remapped_timestamps_are_unique_and_in_utc_order(self):
        for target, kind, start, end in CASES:
            with self.subTest(target=target):
                source = target - timedelta(days=1)
                points = core._series_to_target_points(
                    source_series(source),
                    context=context(),
                    data_source="smard",
                    delivery_date=source,
                    target_date=target,
                )
                actual = [pd.Timestamp(p["ts"]) for p in points]
                expected = list(
                    pd.date_range(start, end, freq="15min", inclusive="left")
                )
                self.assertEqual(actual, expected)
                self.assertEqual(len(actual), len(set(actual)))
                self.assertEqual(
                    [p["value"] for p in points], expected_values(kind, 15)
                )

    def test_transition_reference_and_target_preserve_occurrences(self):
        for source, target in [
            (date(2025, 3, 30), date(2026, 3, 29)),
            (date(2025, 10, 26), date(2026, 10, 25)),
        ]:
            with self.subTest(source=source, target=target):
                series = source_series(source).tz_convert("Europe/Berlin")
                points = core._series_to_target_points(
                    series,
                    context=context(),
                    data_source="entsoe",
                    delivery_date=source,
                    target_date=target,
                )
                self.assertEqual([p["value"] for p in points], series.tolist())

    def test_overnight_entsoe_requests_use_local_midnights(self):
        for source, hours in [(date(2026, 3, 29), 23), (date(2026, 10, 25), 25)]:
            with self.subTest(source=source):
                expected = source_series(source)
                # ENTSO-E can return observations outside the requested range.
                extra = source_series(source + timedelta(days=1)).iloc[:4]
                client = Mock()
                client.query_day_ahead_prices.return_value = pd.concat(
                    [expected, extra]
                )
                with patch.object(core, "EntsoePandasClient", return_value=client):
                    actual = core.fetch_entsoe_series(
                        api_key="unused", context=context(), delivery_date=source
                    )
                call = client.query_day_ahead_prices.call_args.kwargs
                self.assertEqual(call["end"] - call["start"], pd.Timedelta(hours=hours))
                self.assertEqual(call["start"].hour, 0)
                self.assertEqual(call["end"].hour, 0)
                self.assertEqual(call["end"].date(), source + timedelta(days=1))
                pd.testing.assert_series_equal(actual, expected)

    def test_incomplete_or_invalid_point_history_is_rejected(self):
        source = date(2026, 10, 24)
        valid = source_series(source)
        duplicate = valid.copy()
        duplicate.index = (
            valid.index[:9].append(valid.index[8:9]).append(valid.index[10:])
        )
        shifted = valid.copy()
        shifted.index += pd.Timedelta(minutes=1)
        variants = {
            "truncated": valid.iloc[:-1],
            "duplicate": duplicate,
            "off_grid": shifted,
        }
        for label, value in [
            ("null", float("nan")),
            ("infinite", float("inf")),
            ("negative_infinite", float("-inf")),
        ]:
            invalid = valid.copy()
            invalid.iloc[10] = value
            variants[label] = invalid
        for provider in ("smard", "entsoe"):
            for label, series in variants.items():
                with (
                    self.subTest(provider=provider, defect=label),
                    patch.object(core, "_fetch_source_series", return_value=series),
                ):
                    with self.assertRaisesRegex(RuntimeError, "Incomplete or invalid"):
                        core.build_payload_from_source(
                            target_date=date(2026, 10, 25),
                            context=context(),
                            data_source=provider,
                            entsoe_api_key="unused",
                        )

    def test_incomplete_probabilistic_history_uses_point_fallback(self):
        target = date(2026, 10, 25)
        for objective in ("quantile", "ensemble"):
            with self.subTest(objective=objective):

                def fetch(*, delivery_date, **kwargs):
                    series = source_series(delivery_date)
                    return (
                        series
                        if delivery_date == target - timedelta(days=1)
                        else series.iloc[:-1]
                    )

                with patch.object(core, "_fetch_source_series", side_effect=fetch):
                    payload = core.build_payload_from_source(
                        target_date=target,
                        context=context(objective=objective),
                        data_source="smard",
                        entsoe_api_key="unused",
                    )
                self.assertEqual(
                    payload["values"], [[v] * 3 for v in expected_values("autumn", 15)]
                )

    def test_smard_csv_preserves_both_autumn_hour_occurrences(self):
        day = date(2026, 10, 25)
        expected = source_series(day)
        rows = ["Start;End;Value"]
        for ts, value in expected.items():
            local = ts.tz_convert("Europe/Berlin")
            rows.append(f"{local:%b %d, %Y %I:%M %p};;{value}")
        response = Mock(content="\n".join(rows).encode("utf-8"))
        with patch.object(core.requests, "post", return_value=response):
            actual = core.fetch_smard_series(context=context(), delivery_date=day)
        pd.testing.assert_series_equal(actual, expected, check_freq=False)


if __name__ == "__main__":
    unittest.main()
