#~/bin/bash

#/usr/local/bin/ctypesgen -l \
/home/user/.local/bin/ctypesgen \
	-l libiec61850.so.1.4.2 \
	-I /usr/local/include/libiec61850 \
	src/common/inc/libiec61850_common_api.h \
	src/common/inc/linked_list.h src/iec61850/inc/iec61850_client.h \
	src/iec61850/inc/iec61850_common.h src/iec61850/inc/iec61850_server.h \
	src/iec61850/inc/iec61850_model.h \
	src/iec61850/inc/iec61850_cdc.h \
	src/iec61850/inc/iec61850_dynamic_model.h \
	src/iec61850/inc/iec61850_config_file_parser.h \
	src/mms/inc/mms_value.h src/mms/inc/mms_common.h \
	src/mms/inc/mms_types.h src/mms/inc/mms_type_spec.h \
	src/mms/inc/mms_client_connection.h \
	src/mms/inc/iso_connection_parameters.h \
	src/sampled_values/sv_subscriber.h \
	src/sampled_values/sv_publisher.h \
	src/goose/goose_publisher.h \
	src/goose/goose_receiver.h \
	src/goose/goose_subscriber.h \
	-o lib61850.py

