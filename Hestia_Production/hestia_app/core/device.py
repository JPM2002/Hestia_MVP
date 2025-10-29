from user_agents import parse as parse_ua

def detect(ua_string: str) -> dict:
    try:
        ua = parse_ua(ua_string or '')
        if ua.is_mobile and not ua.is_tablet:
            cls = 'mobile'
        elif ua.is_tablet:
            cls = 'tablet'
        else:
            cls = 'desktop'
        return {'class': cls, 'is_mobile': cls=='mobile', 'is_tablet': cls=='tablet', 'is_desktop': cls=='desktop'}
    except Exception:
        return {'class':'desktop','is_mobile':False,'is_tablet':False,'is_desktop':True}
