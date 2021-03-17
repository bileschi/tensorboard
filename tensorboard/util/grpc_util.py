# Copyright 2019 The TensorFlow Authors. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
# ==============================================================================
"""Utilities for working with python gRPC stubs."""


import enum
import random
import time

import grpc

from tensorboard import version
from tensorboard.util import tb_logging

logger = tb_logging.get_logger()

# Default RPC timeout.
_GRPC_DEFAULT_TIMEOUT_SECS = 30

# Max number of times to attempt an RPC, retrying on transient failures.
_GRPC_RETRY_MAX_ATTEMPTS = 5

# Parameters to control the exponential backoff behavior.
_GRPC_RETRY_EXPONENTIAL_BASE = 2
_GRPC_RETRY_JITTER_FACTOR_MIN = 1.1
_GRPC_RETRY_JITTER_FACTOR_MAX = 1.5

# Status codes from gRPC for which it's reasonable to retry the RPC.
_GRPC_RETRYABLE_STATUS_CODES = frozenset(
    [
        grpc.StatusCode.ABORTED,
        grpc.StatusCode.DEADLINE_EXCEEDED,
        grpc.StatusCode.RESOURCE_EXHAUSTED,
        grpc.StatusCode.UNAVAILABLE,
    ]
)

# gRPC metadata key whose value contains the client version.
_VERSION_METADATA_KEY = "tensorboard-version"


def async_call(
    api_method,
    request,
    completion_handler,
    ):
    """Call a gRPC stub API method.

    This only supports unary-unary RPCs: i.e., no streaming on either end.
    Streamed RPCs will generally need application-level pagination support,
    because after a gRPC error one must retry the entire request; there is no
    "retry-resume" functionality.

    Args:
      api_method: Callable for the API method to invoke.
      request: Request protocol buffer to pass to the API method.
      completion_handler: A callback which takes the resolved future as an
        argument and completes the computation.

    Returns:
      None.  All computation relying on the return value of the gRPC should
        be done in the completion_handler.
    """
    # We can't actually use api_method.__name__ because it's not a real method,
    # it's a special gRPC callable instance that doesn't expose the method name.
    rpc_name = request.__class__.__name__.replace("Request", "")
    logger.debug("Async RPC call %s with request: %r", rpc_name, request)
    future = api_method.future(
        request,
        timeout=_GRPC_DEFAULT_TIMEOUT_SECS,
        metadata=version_metadata(),
    )
    future.add_done_callback(completion_handler)

def async_call_with_retries(
    api_method,
    request,
    completion_handler,
    num_remaining_tries=_GRPC_RETRY_MAX_ATTEMPTS - 1,
    clock=None
    ):
    """ TO DO DO NOT SUBMIT...
    """
    print(f"START async_call_with_retries({num_remaining_tries})")
    if num_remaining_tries < 0:
        # This should not happen in the course of normal operations and
        # indicates a bug in the implementation.
        raise ValueError(
            "num_remaining_tries=%d. expected >= 0." % num_remaining_tries)
    # We can't actually use api_method.__name__ because it's not a real method,
    # it's a special gRPC callable instance that doesn't expose the method name.
    rpc_name = request.__class__.__name__.replace("Request", "")
    logger.debug("Async RPC call %s with request: %r", rpc_name, request)
    future = api_method.future(
        request,
        timeout=_GRPC_DEFAULT_TIMEOUT_SECS,
        metadata=version_metadata(),
    )
    # The continuation should wrap the completion_handler such that:
    # if the grpc call succeeds, we should invoke the completion_handler.
    # if there are no more retries, we should invoke the completion_handler.
    # Otherwise, we should invoke async_call_with_retries with one less
    # retry.
    # are no more retries)
    #
    def retry_handler(future):
        print("start of async_call_with_retries.retry_handler")
        e = future.exception()
        if e is None:
            print("e is None :  async_call_with_retries.retry_handler")
            completion_handler(future)
            return
        else:
            logger.info("RPC call %s got error %s", rpc_name, e)
            # If unable to retry, proceed to completion_handler.
            if e.code() not in _GRPC_RETRYABLE_STATUS_CODES:
                completion_handler(future)
                return
            if num_remaining_tries <= 0:
                completion_handler(future)
                return
            # If able to retry, wait then do so.
            num_attempts = _GRPC_RETRY_MAX_ATTEMPTS - num_remaining_tries
            backoff_secs = _compute_backoff_seconds(num_attempts)
            clock.sleep(backoff_secs)
            async_call_with_retries(
                api_method, request, completion_handler, num_remaining_tries - 1, clock)

    print("adding future to callback")
    future.add_done_callback(retry_handler)



def _compute_backoff_seconds(num_attempts):
    """Compute wait time between attempts."""
    jitter_factor = random.uniform(
        _GRPC_RETRY_JITTER_FACTOR_MIN, _GRPC_RETRY_JITTER_FACTOR_MAX
    )
    backoff_secs = (
        _GRPC_RETRY_EXPONENTIAL_BASE ** num_attempts
    ) * jitter_factor
    return backoff_secs

def call_with_retries(api_method, request, clock=None):
    """Call a gRPC stub API method, with automatic retry logic.

    This only supports unary-unary RPCs: i.e., no streaming on either end.
    Streamed RPCs will generally need application-level pagination support,
    because after a gRPC error one must retry the entire request; there is no
    "retry-resume" functionality.

    Args:
      api_method: Callable for the API method to invoke.
      request: Request protocol buffer to pass to the API method.
      clock: an interface object supporting `time()` and `sleep()` methods
        like the standard `time` module; if not passed, uses the normal module.

    Returns:
      Response protocol buffer returned by the API method.

    Raises:
      grpc.RpcError: if a non-retryable error is returned, or if all retry
        attempts have been exhausted.
    """
    if clock is None:
        clock = time
    # We can't actually use api_method.__name__ because it's not a real method,
    # it's a special gRPC callable instance that doesn't expose the method name.
    rpc_name = request.__class__.__name__.replace("Request", "")
    logger.debug("RPC call %s with request: %r", rpc_name, request)
    num_attempts = 0
    while True:
        num_attempts += 1
        try:
            return api_method(
                request,
                timeout=_GRPC_DEFAULT_TIMEOUT_SECS,
                metadata=version_metadata(),
            )
        except grpc.RpcError as e:
            logger.info("RPC call %s got error %s", rpc_name, e)
            if e.code() not in _GRPC_RETRYABLE_STATUS_CODES:
                raise
            if num_attempts >= _GRPC_RETRY_MAX_ATTEMPTS:
                raise
        backoff_secs = _compute_backoff_seconds(num_attempts)
        logger.info(
            "RPC call %s attempted %d times, retrying in %.1f seconds",
            rpc_name,
            num_attempts,
            backoff_secs,
        )
        clock.sleep(backoff_secs)


def version_metadata():
    """Creates gRPC invocation metadata encoding the TensorBoard version.

    Usage: `stub.MyRpc(request, metadata=version_metadata())`.

    Returns:
      A tuple of key-value pairs (themselves 2-tuples) to be passed as the
      `metadata` kwarg to gRPC stub API methods.
    """
    return ((_VERSION_METADATA_KEY, version.VERSION),)


def extract_version(metadata):
    """Extracts version from invocation metadata.

    The argument should be the result of a prior call to `metadata` or the
    result of combining such a result with other metadata.

    Returns:
      The TensorBoard version listed in this metadata, or `None` if none
      is listed.
    """
    return dict(metadata).get(_VERSION_METADATA_KEY)


@enum.unique
class ChannelCredsType(enum.Enum):
    LOCAL = "local"
    SSL = "ssl"
    SSL_DEV = "ssl_dev"

    def channel_config(self):
        """Create channel credentials and options.

        Returns:
          A tuple `(channel_creds, channel_options)`, where `channel_creds`
          is a `grpc.ChannelCredentials` and `channel_options` is a
          (potentially empty) list of `(key, value)` tuples. Both results
          may be passed to `grpc.secure_channel`.
        """

        options = []
        if self == ChannelCredsType.LOCAL:
            creds = grpc.local_channel_credentials()
        elif self == ChannelCredsType.SSL:
            creds = grpc.ssl_channel_credentials()
        elif self == ChannelCredsType.SSL_DEV:
            # Configure the dev cert to use by passing the environment variable
            # GRPC_DEFAULT_SSL_ROOTS_FILE_PATH=path/to/cert.crt
            creds = grpc.ssl_channel_credentials()
            options.append(("grpc.ssl_target_name_override", "localhost"))
        else:
            raise AssertionError("unhandled ChannelCredsType: %r" % self)
        return (creds, options)

    @classmethod
    def choices(cls):
        return cls.__members__.values()

    def __str__(self):
        # Use user-facing string, because this is shown for flag choices.
        return self.value
