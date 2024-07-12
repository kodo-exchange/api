# -*- coding: utf-8 -*-

import json
from datetime import timedelta

import falcon
from multicall import Call, Multicall

from app.settings import CACHE, DEFAULT_TOKEN_ADDRESS, LOGGER, VE_ADDRESS
from app.gauges import Gauge
from app.pairs import Pair, Pairs
from app.assets import Token


class Stats(object):
    """Handles stats info"""

    CACHE_KEY = 'stats:json'
    CACHE_TIME = timedelta(minutes=5)

    @classmethod
    def recache(cls):
        supply_multicall = Multicall([
            Call(
                DEFAULT_TOKEN_ADDRESS,
                'decimals()(uint256)',
                [['token_decimals', None]]
            ),
            Call(
                VE_ADDRESS,
                'decimals()(uint256)',
                [['lock_decimals', None]]
            ),
            Call(
                DEFAULT_TOKEN_ADDRESS,
                'totalSupply()(uint256)',
                [['raw_total_supply', None]]
            ),
            Call(
                DEFAULT_TOKEN_ADDRESS,
                ['balanceOf(address)(uint256)', VE_ADDRESS],
                [['raw_locked_supply', None]]
            ),
        ])

        data = supply_multicall()

        data['total_supply'] = \
            data['raw_total_supply'] / 10**data['token_decimals']
        data['locked_supply'] = \
            data['raw_locked_supply'] / 10**data['lock_decimals']
        data['circulating_supply'] = \
            data['total_supply'] - data['locked_supply']

        pairs = Pairs.serialize()
        default_token = Token.find(DEFAULT_TOKEN_ADDRESS)
        rebase_apr = Gauge.rebase_apr()

        tbv_sum = 0
        votes_sum = 0
        for pair in pairs:
            if 'gauge' in pair and 'tbv' in pair['gauge'] and 'votes' in pair['gauge']:
                tbv_sum += pair['gauge']['tbv']
                votes_sum += pair['gauge']['votes']

        apr = rebase_apr
        if votes_sum * default_token.price > 0:
            apr += ((tbv_sum * 52) / (votes_sum * default_token.price)) * 100
        
        incentive_per_vote = 0
        if votes_sum > 0:
            incentive_per_vote = tbv_sum / votes_sum
        else:
            incentive_per_vote = tbv_sum
        
        data['apr'] = apr
        data['market_cap'] = data['total_supply'] * default_token.price
        data['incentive'] = tbv_sum
        data['incentive_per_vote'] = incentive_per_vote

        stats_data = json.dumps(dict(data=data))

        CACHE.setex(cls.CACHE_KEY, cls.CACHE_TIME, stats_data)
        LOGGER.debug('Cache updated for %s.', cls.CACHE_KEY)

        return stats_data

    def on_get(self, req, resp):
        """Caches and returns our stats info"""
        stats_data = CACHE.get(self.CACHE_KEY) or Stats.recache()

        resp.text = stats_data
        resp.status = falcon.HTTP_200
