import pytest
from app.sanctions import (
    approved_redirect_url,
    parse_official_dataset,
    validate_source_url,
)


def test_ofac_xml_parser_preserves_alias_and_country():
    records = parse_official_dataset(
        "OFAC",
        b"""<?xml version="1.0"?>
        <sdnList><sdnEntry><uid>42</uid><firstName>Example</firstName>
        <lastName>Trading</lastName><akaList><aka><firstName>Example</firstName>
        <lastName>Exports</lastName></aka></akaList>
        <addressList><address><country>XZ</country></address></addressList>
        </sdnEntry></sdnList>""",
    )
    assert records[0].external_id == "42"
    assert records[0].primary_name == "Example Trading"
    assert records[0].aliases == ["Example Exports"]
    assert records[0].countries == ["XZ"]


def test_un_xml_parser_supports_individual_and_entity():
    records = parse_official_dataset(
        "UN",
        b"""<CONSOLIDATED_LIST>
        <INDIVIDUALS><INDIVIDUAL><DATAID>i-1</DATAID>
        <FIRST_NAME>Ada</FIRST_NAME><SECOND_NAME>Example</SECOND_NAME>
        <INDIVIDUAL_ALIAS><ALIAS_NAME>A. Example</ALIAS_NAME></INDIVIDUAL_ALIAS>
        </INDIVIDUAL></INDIVIDUALS>
        <ENTITIES><ENTITY><DATAID>e-1</DATAID>
        <FIRST_NAME>Example Group</FIRST_NAME></ENTITY></ENTITIES>
        </CONSOLIDATED_LIST>""",
    )
    assert [record.external_id for record in records] == ["i-1", "e-1"]
    assert records[0].aliases == ["A. Example"]


def test_eu_xml_parser_supports_fsf_shape():
    records = parse_official_dataset(
        "EU",
        b"""<export><sanctionsEntity logicalId="eu-1">
        <nameAlias wholeName="Example Entity"/>
        <nameAlias wholeName="Example Holdings"/>
        <address countryIso2Code="XZ"/>
        </sanctionsEntity></export>""",
    )
    assert records[0].primary_name == "Example Entity"
    assert records[0].aliases == ["Example Holdings"]


def test_parser_blocks_doctype_and_source_url_ssrf():
    with pytest.raises(ValueError, match="DOCTYPE"):
        parse_official_dataset("UN", b"<!DOCTYPE foo><CONSOLIDATED_LIST/>")
    with pytest.raises(ValueError, match="NOT_APPROVED"):
        validate_source_url("OFAC", "http://127.0.0.1/internal")


def test_redirect_is_validated_before_following():
    target = (
        "https://wc2h-sls-prod-public-published.s3.us-gov-west-1.amazonaws.com/"
        "sdn.xml"
    )
    assert (
        approved_redirect_url(
            "OFAC",
            "https://sanctionslistservice.ofac.treas.gov/list",
            target,
        )
        == target
    )
    with pytest.raises(ValueError, match="SANCTIONS_SOURCE_URL_NOT_APPROVED"):
        approved_redirect_url(
            "OFAC",
            "https://sanctionslistservice.ofac.treas.gov/list",
            "http://169.254.169.254/latest/meta-data",
        )
