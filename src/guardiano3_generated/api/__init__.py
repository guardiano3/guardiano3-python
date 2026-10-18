# flake8: noqa

if __import__("typing").TYPE_CHECKING:
    # import apis into api package
    from guardiano3_generated.api.v1_account_api import V1AccountApi
    from guardiano3_generated.api.v1_analysis_api import V1AnalysisApi
    from guardiano3_generated.api.v1_api_keys_api import V1ApiKeysApi
    from guardiano3_generated.api.v1_auth_api import V1AuthApi
    from guardiano3_generated.api.v1_auth_web_api import V1AuthWebApi
    from guardiano3_generated.api.v1_org_api import V1OrgApi
    from guardiano3_generated.api.v1_policies_api import V1PoliciesApi
    from guardiano3_generated.api.v1_sessions_api import V1SessionsApi
    from guardiano3_generated.api.v1_site_api import V1SiteApi
    
else:
    from lazy_imports import LazyModule, as_package, load

    load(
        LazyModule(
            *as_package(__file__),
            """# import apis into api package
from guardiano3_generated.api.v1_account_api import V1AccountApi
from guardiano3_generated.api.v1_analysis_api import V1AnalysisApi
from guardiano3_generated.api.v1_api_keys_api import V1ApiKeysApi
from guardiano3_generated.api.v1_auth_api import V1AuthApi
from guardiano3_generated.api.v1_auth_web_api import V1AuthWebApi
from guardiano3_generated.api.v1_org_api import V1OrgApi
from guardiano3_generated.api.v1_policies_api import V1PoliciesApi
from guardiano3_generated.api.v1_sessions_api import V1SessionsApi
from guardiano3_generated.api.v1_site_api import V1SiteApi

""",
            name=__name__,
            doc=__doc__,
        )
    )
