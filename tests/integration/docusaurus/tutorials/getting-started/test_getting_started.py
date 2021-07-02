from ruamel import yaml

import great_expectations as ge
from great_expectations.checkpoint import SimpleCheckpoint
from great_expectations.core.batch import BatchRequest
from great_expectations.profile.user_configurable_profiler import (
    UserConfigurableProfiler,
)
from great_expectations.validator.validator import Validator

context = ge.get_context()

assert context

# adding datasource
datasource_yaml = f"""
name: data__dir
class_name: Datasource
module_name: great_expectations.datasource
execution_engine:
  module_name: great_expectations.execution_engine
  class_name: PandasExecutionEngine
data_connectors:
    default_runtime_data_connector_name:
        class_name: RuntimeDataConnector
        batch_identifiers:
            - default_identifier_name
    default_inferred_data_connector_name:
        class_name: InferredAssetFilesystemDataConnector
        base_directory: ../data/
        default_regex:
          group_names:
            - data_asset_name
          pattern: (.*)
"""
context.test_yaml_config(datasource_yaml)
context.add_datasource(**yaml.load(datasource_yaml))

# creating expectation suite
batch_request = {
    "datasource_name": "data__dir",
    "data_connector_name": "default_inferred_data_connector_name",
    "data_asset_name": "yellow_trip_data_sample_2019-01.csv",
    "limit": 1000,
}
expectation_suite_name = "taxi.demo"
context.create_expectation_suite(
    expectation_suite_name=expectation_suite_name, overwrite_existing=False
)
validator = context.get_validator(
    batch_request=BatchRequest(**batch_request),
    expectation_suite_name=expectation_suite_name,
)
assert isinstance(validator, Validator)

ignored_columns = [
    "vendor_id",
    "pickup_datetime",
    "dropoff_datetime",
    # "passenger_count",
    "trip_distance",
    "rate_code_id",
    "store_and_fwd_flag",
    "pickup_location_id",
    "dropoff_location_id",
    "payment_type",
    "fare_amount",
    "extra",
    "mta_tax",
    "tip_amount",
    "tolls_amount",
    "improvement_surcharge",
    "total_amount",
    "congestion_surcharge",
]

profiler = UserConfigurableProfiler(
    profile_dataset=validator,
    excluded_expectations=None,
    ignored_columns=ignored_columns,
    not_null_only=False,
    primary_or_compound_key=False,
    semantic_types_dict=None,
    table_expectations_only=False,
    value_set_threshold="MANY",
)
suite = profiler.build_suite()
validator.save_expectation_suite(discard_failed_expectations=False)

my_checkpoint_config = f"""
name: my_checkpoint
config_version: 1.0
class_name: SimpleCheckpoint
run_name_template: "%Y%m%d-%H%M%S-my-run-name-template"
validations:
  - batch_request:
      datasource_name: data__dir
      data_connector_name: default_inferred_data_connector_name
      data_asset_name: yellow_trip_data_sample_2019-02.csv
      data_connector_query:
        index: -1
    expectation_suite_name: taxi.demo
"""

# Note : site_names are set to None because we are not actually updating and building data_docs in this test.
my_checkpoint_config = yaml.load(my_checkpoint_config)

checkpoint = SimpleCheckpoint(
    **my_checkpoint_config, data_context=context, site_names=None
)
checkpoint_result = checkpoint.run(site_names=None)
assert checkpoint_result.run_results