def resolve(profile,family,source_format):
    if profile is None or source_format not in profile.source_formats:return 'UNKNOWN'
    if family in profile.supported_families:return 'SUPPORTED'
    if family in profile.unsupported_families:return 'UNSUPPORTED'
    return 'UNKNOWN'
