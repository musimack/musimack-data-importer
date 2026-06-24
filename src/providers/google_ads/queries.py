from __future__ import annotations


def build_campaign_performance_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          campaign.id,
          campaign.name,
          campaign.status,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.average_cpc,
          metrics.ctr,
          metrics.cost_per_conversion
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
    ).format(start_date=start_date, end_date=end_date)


def build_keyword_performance_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          campaign.name,
          ad_group_criterion.keyword.text,
          ad_group_criterion.keyword.match_type,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.average_cpc,
          metrics.ctr
        FROM keyword_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
          AND ad_group_criterion.type = KEYWORD
        """
    ).format(start_date=start_date, end_date=end_date)


def build_search_term_performance_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          campaign.name,
          ad_group.name,
          search_term_view.search_term,
          search_term_view.status,
          segments.keyword.info.text,
          segments.keyword.info.match_type,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.ctr
        FROM search_term_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
    ).format(start_date=start_date, end_date=end_date)


def build_landing_page_performance_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          expanded_landing_page_view.expanded_final_url,
          campaign.name,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions,
          metrics.ctr
        FROM expanded_landing_page_view
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
    ).format(start_date=start_date, end_date=end_date)


def build_time_series_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          campaign.name,
          segments.date,
          metrics.impressions,
          metrics.clicks,
          metrics.cost_micros,
          metrics.conversions
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
    ).format(start_date=start_date, end_date=end_date)


def build_budget_pacing_query(start_date: str, end_date: str) -> str:
    return _format_query(
        """
        SELECT
          campaign.name,
          campaign.status,
          campaign_budget.amount_micros,
          metrics.cost_micros
        FROM campaign
        WHERE segments.date BETWEEN '{start_date}' AND '{end_date}'
        """
    ).format(start_date=start_date, end_date=end_date)


def _format_query(query: str) -> str:
    return "\n".join(line.rstrip() for line in query.strip().splitlines())
