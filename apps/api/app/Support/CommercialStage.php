<?php

namespace App\Support;

/**
 * §3's commercial funnel, and the rules about moving through it.
 *
 * One class rather than scattered string comparisons because three things ask
 * about stages — the API, the dashboard, and the Python engine's suggestion
 * logic — and a funnel whose order is written down in three places has three
 * funnels.
 */
final class CommercialStage
{
    /**
     * §3's funnel, in order. The array order IS the progression: `indexOf` is
     * how "is this a promotion or a demotion" gets answered, so reordering this
     * list changes behaviour and is not a cosmetic edit.
     */
    public const ORDER = [
        'observed',
        'investigating',
        'buyer_identified',
        'problem_validated',
        'commercially_validated',
        'paid_pilot',
        'repeatable_solution',
        'product_candidate',
        'saas_or_managed_service',
    ];

    /**
     * Stages a human may only reach with evidence behind them, mapped to the
     * §7 gate that supplies it.
     *
     * The earlier stages are deliberately ungated: `investigating` means someone
     * decided to look, which needs no evidence, and gating a decision to pay
     * attention would just teach people to skip recording it.
     */
    public const GATED = [
        'buyer_identified' => 'Gate 1 — a buyer hypothesis must be recorded (target_buyer)',
        'problem_validated' => 'Gate 2 — at least one interview confirming the problem',
        'commercially_validated' => 'Gate 3 — two independent businesses confirming, plus one strong commercial signal',
        'paid_pilot' => 'Gate 4 — recorded evidence that a customer paid',
        'repeatable_solution' => 'Gate 5 — a second paying business with substantially the same problem',
    ];

    public const LABELS = [
        'observed' => 'Observed',
        'investigating' => 'Investigating',
        'buyer_identified' => 'Buyer identified',
        'problem_validated' => 'Problem validated',
        'commercially_validated' => 'Commercially validated',
        'paid_pilot' => 'Paid pilot',
        'repeatable_solution' => 'Repeatable solution',
        'product_candidate' => 'Product candidate',
        'saas_or_managed_service' => 'SaaS / managed service',
    ];

    public static function isValid(string $stage): bool
    {
        return in_array($stage, self::ORDER, true);
    }

    public static function rank(string $stage): int
    {
        $index = array_search($stage, self::ORDER, true);

        return $index === false ? -1 : $index;
    }

    public static function isAdvance(string $from, string $to): bool
    {
        return self::rank($to) > self::rank($from);
    }

    /**
     * Whether the recorded evidence supports a stage.
     *
     * Returns [bool, string|null] — allowed, and the reason if not. The reason
     * matters more than the boolean: "you cannot promote this" is useless
     * feedback, "Gate 3 needs a second independent business" tells someone what
     * to go and do.
     *
     * Demotions are always allowed and never gated. Deciding an opportunity was
     * over-promoted is exactly the correction the funnel needs to permit; making
     * it hard would leave stale optimistic stages in place.
     */
    public static function gateCheck(string $to, array $evidence): array
    {
        if (! array_key_exists($to, self::GATED)) {
            return [true, null];
        }

        $reason = self::GATED[$to];

        return match ($to) {
            'buyer_identified' => $evidence['has_buyer_hypothesis']
                ? [true, null]
                : [false, $reason],

            'problem_validated' => $evidence['problem_confirmed_count'] >= 1
                ? [true, null]
                : [false, $reason],

            // §7 Gate 3: multiple independent businesses AND one strong signal.
            // Both halves, not either — "several people agree it is annoying"
            // without a single commercial signal is what the gate exists to stop.
            'commercially_validated' => $evidence['independent_confirmations'] >= 2
                && $evidence['has_strong_commercial_signal']
                    ? [true, null]
                    : [false, $reason],

            // Gate 4 is money changing hands. Nothing else substitutes.
            'paid_pilot' => $evidence['paid_pilot_count'] >= 1
                ? [true, null]
                : [false, $reason],

            // Gate 5 is a *second* paying business, which is why it counts
            // distinct company_refs rather than payment events. Two pilots with
            // the same customer prove retention, not repeatability.
            'repeatable_solution' => $evidence['paying_business_count'] >= 2
                ? [true, null]
                : [false, $reason],

            default => [true, null],
        };
    }

    /**
     * Gate-check every stage from just after `from` up to and including `to`.
     *
     * Checking only the destination would let an advance skip a stage whose gate
     * is unmet — reaching `problem_validated` from `investigating` with no buyer
     * hypothesis recorded, for instance. That state is one `suggestFrom()` can
     * never produce, since it stops at the first failing gate, so allowing it
     * would leave the API and the engine disagreeing about what the funnel
     * contains.
     *
     * Reports the FIRST unmet gate rather than all of them: that is the one to
     * go and satisfy, and a list of five would bury it.
     */
    public static function gateCheckPath(string $from, string $to, array $evidence): array
    {
        $fromRank = self::rank($from);
        $toRank = self::rank($to);

        foreach (self::ORDER as $index => $stage) {
            if ($index <= $fromRank || $index > $toRank) {
                continue;
            }

            [$allowed, $reason] = self::gateCheck($stage, $evidence);
            if (! $allowed) {
                return [false, $reason, $stage];
            }
        }

        return [true, null, null];
    }

    /**
     * The furthest stage the recorded evidence supports — the engine's
     * suggestion, never an automatic promotion (§52).
     *
     * Walks forward from the start and stops at the first gate that fails, so a
     * suggestion is always a stage whose every predecessor is also satisfied.
     * Jumping to the highest individually-passing gate would suggest
     * `repeatable_solution` for an opportunity with two paying customers and no
     * recorded interviews, which is not a state the funnel describes.
     */
    public static function suggestFrom(array $evidence): string
    {
        $suggested = 'observed';

        foreach (self::ORDER as $stage) {
            if ($stage === 'observed') {
                continue;
            }

            // Beyond paid_pilot/repeatable_solution the funnel stops being about
            // evidence and starts being about build decisions (§7 Gate 5: "only
            // now should major SaaS investment begin"). The engine has no
            // business suggesting those.
            if (in_array($stage, ['product_candidate', 'saas_or_managed_service'], true)) {
                break;
            }

            // `investigating` is the one ungated step, and suggesting it the
            // moment any signal exists would make the suggestion meaningless.
            // It needs a reason to look: some human contact has happened.
            if ($stage === 'investigating') {
                if ($evidence['interview_count'] < 1 && $evidence['evidence_count'] < 1) {
                    break;
                }
                $suggested = $stage;

                continue;
            }

            [$allowed] = self::gateCheck($stage, $evidence);
            if (! $allowed) {
                break;
            }

            $suggested = $stage;
        }

        return $suggested;
    }
}
