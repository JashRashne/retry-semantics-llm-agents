#!/usr/bin/env python3
"""Operator entry point for the two-stage Stripe engineering gate."""

from retry_semantics.study2.stripe_live_qualification import main


if __name__ == "__main__":
    raise SystemExit(main())
