AREA_SLUGS = {'mantencion': 'MANTENCION'}
def area_from_slug(slug): return AREA_SLUGS.get(slug)
def default_area_for_user(u): return 'MANTENCION'
