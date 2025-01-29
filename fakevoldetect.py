def detect_fake_volume(data):
    """
    Simple heuristic to detect fake volume:
    - High volume with low liquidity.
    - Large trades from the same address (not implemented here).
    """
    liquidity = data["liquidity"]
    volume = data["volume"]

    # Example heuristic: Volume > 10x liquidity is suspicious
    if liquidity > 0 and volume / liquidity > 10:
        return True
    return False
