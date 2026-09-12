"""How the field is split into groups (problem statement §9).

The rule that matters: every group is near-equal in size, so every group is
topped up with the same number of fillers give or take one. Scoring standardises
a block across the whole table, fillers included, and fillers are deliberately
naive, so a group carrying more of them is measured against a weaker field.
"""

import random

from harness.simulate import BotSpec, make_groups, pad_to_group

GROUP_SIZE = 20


def field(n: int) -> list[BotSpec]:
    return [BotSpec(key=f"BOT{i:04d}", path=f"/tmp/BOT{i:04d}_1.py") for i in range(n)]


def sizes(groups) -> list[int]:
    return [len(g) for g in groups]


class TestTheSplitIsEven:
    """Both draws partition the field the same way."""

    def test_the_field_splits_into_ceil_n_over_group_size_groups(self):
        for n, expected in [(1, 1), (20, 1), (21, 2), (54, 3), (84, 5), (100, 5)]:
            groups = make_groups(field(n), GROUP_SIZE, random.Random(1))
            assert len(groups) == expected, f"{n} bots"

    def test_group_sizes_never_differ_by_more_than_one(self):
        for n in range(1, 130):
            for seeding in (None, {}):
                groups = make_groups(
                    field(n), GROUP_SIZE, random.Random(n),
                    seeding=({f"BOT{i:04d}": float(i) for i in range(n)} if seeding == {} else None),
                )
                assert max(sizes(groups)) - min(sizes(groups)) <= 1, f"{n} bots"

    def test_no_group_is_larger_than_the_group_size(self):
        """The old random draw folded a short remainder into the previous group,
        which produced tables of 21 and 24 for 41 and 84 bots."""
        for n in range(1, 130):
            groups = make_groups(field(n), GROUP_SIZE, random.Random(n))
            assert max(sizes(groups)) <= GROUP_SIZE, f"{n} bots"

    def test_the_worked_examples(self):
        assert sizes(make_groups(field(54), GROUP_SIZE, random.Random(0))) == [18, 18, 18]
        assert sizes(make_groups(field(84), GROUP_SIZE, random.Random(0))) == [17, 17, 17, 17, 16]
        # The last row of the snake runs right to left, so the odd bot out lands
        # in the later groups rather than the first.
        assert sizes(make_groups(field(41), GROUP_SIZE, random.Random(0))) == [13, 14, 14]

    def test_a_random_draw_and_a_seeded_draw_partition_alike(self):
        """An iteration's standardised scores are only comparable with another
        iteration's if both played the same shape of table."""
        for n in (37, 54, 84, 119):
            seeding = {f"BOT{i:04d}": float(i) for i in range(n)}
            blind = make_groups(field(n), GROUP_SIZE, random.Random(7))
            seeded = make_groups(field(n), GROUP_SIZE, random.Random(7), seeding=seeding)
            assert sorted(sizes(blind)) == sorted(sizes(seeded)), f"{n} bots"

    def test_everybody_plays_exactly_once(self):
        for n in (1, 19, 20, 21, 54, 84):
            groups = make_groups(field(n), GROUP_SIZE, random.Random(3))
            keys = [spec.key for group in groups for spec in group]
            assert sorted(keys) == sorted(s.key for s in field(n)), f"{n} bots"

    def test_an_empty_field_is_one_empty_group(self):
        assert make_groups([], GROUP_SIZE, random.Random(0)) == [[]]


class TestFillerExposureIsEqual:
    """What the even split is actually for."""

    def test_every_group_carries_the_same_fillers_give_or_take_one(self):
        for n in range(1, 130):
            groups = make_groups(field(n), GROUP_SIZE, random.Random(n))
            fillers = [
                sum(1 for spec in pad_to_group(group, GROUP_SIZE) if spec.is_filler)
                for group in groups
            ]
            assert max(fillers) - min(fillers) <= 1, f"{n} bots: {fillers}"

    def test_fifty_four_bots_no_longer_hand_one_group_every_filler(self):
        groups = make_groups(field(54), GROUP_SIZE, random.Random(0))
        fillers = [
            sum(1 for spec in pad_to_group(group, GROUP_SIZE) if spec.is_filler)
            for group in groups
        ]
        assert fillers == [2, 2, 2]  # was [0, 0, 6]

    def test_every_table_is_full(self):
        for n in (1, 37, 54, 84):
            for group in make_groups(field(n), GROUP_SIZE, random.Random(5)):
                assert len(pad_to_group(group, GROUP_SIZE)) == GROUP_SIZE


class TestSeededGroupsStayBalanced:
    def test_the_snake_spreads_strength_across_groups(self):
        """Balanced, not segregated: group means should sit far closer together
        than cutting the sorted field into blocks would put them."""
        n = 84
        seeding = {f"BOT{i:04d}": float(n - i) for i in range(n)}
        groups = make_groups(field(n), GROUP_SIZE, random.Random(0), seeding=seeding)

        def mean_of(group):
            return sum(seeding[spec.key] for spec in group) / len(group)

        snake_spread = max(map(mean_of, groups)) - min(map(mean_of, groups))

        # What segregation would look like: the sorted field cut into blocks.
        ordered = sorted(field(n), key=lambda s: -seeding[s.key])
        per = len(ordered) // len(groups)
        blocks = [ordered[i:i + per] for i in range(0, len(ordered), per)]
        segregated_spread = max(map(mean_of, blocks)) - min(map(mean_of, blocks))

        assert snake_spread < segregated_spread / 5

    def test_the_strongest_bots_are_not_all_in_one_group(self):
        n = 60
        seeding = {f"BOT{i:04d}": float(n - i) for i in range(n)}
        groups = make_groups(field(n), GROUP_SIZE, random.Random(0), seeding=seeding)
        top_ten = {f"BOT{i:04d}" for i in range(10)}

        per_group = [sum(1 for spec in group if spec.key in top_ten) for group in groups]
        assert max(per_group) <= len(top_ten) // len(groups) + 1

    def test_a_seeded_draw_is_reproducible(self):
        n = 54
        seeding = {f"BOT{i:04d}": float(i) for i in range(n)}
        a = make_groups(field(n), GROUP_SIZE, random.Random(11), seeding=seeding)
        b = make_groups(field(n), GROUP_SIZE, random.Random(11), seeding=seeding)
        assert [[s.key for s in g] for g in a] == [[s.key for s in g] for g in b]

    def test_a_blind_draw_is_reproducible_from_its_seed(self):
        a = make_groups(field(54), GROUP_SIZE, random.Random(11))
        b = make_groups(field(54), GROUP_SIZE, random.Random(11))
        assert [[s.key for s in g] for g in a] == [[s.key for s in g] for g in b]

    def test_a_blind_draw_actually_shuffles(self):
        groups = make_groups(field(54), GROUP_SIZE, random.Random(2))
        dealt = [spec.key for group in groups for spec in group]
        assert dealt != sorted(dealt)
