# Copyright 2013 Google Inc. All Rights Reserved.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS-IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Db models for the XBlock datastore entities."""

__author__ = 'John Orr (jorr@google.com)'

import re

from models import entities
from google.appengine.ext import db


class DefinitionEntity(entities.BaseEntity):
    data = db.TextProperty(indexed=False)


class UsageEntity(entities.BaseEntity):
    data = db.TextProperty(indexed=False)


class KeyValueEntity(entities.BaseEntity):
    _BLOCK_ID_RE = re.compile('^[0-9a-zA-Z]{32}$')

    data = db.TextProperty(indexed=False)

    @classmethod
    def safe_key(cls, db_key, transform_fn):
        """Creates a copy of db_key that is safe for export."""

        key_list = db_key.name().split('.')

        assert len(key_list) in {3, 4}
        assert key_list[0] in {
            'children', 'parent', 'usage', 'definition', 'type', 'all'}
        assert cls._BLOCK_ID_RE.match(key_list[1])

        if len(key_list) == 4:
            key_list[2] = transform_fn(key_list[2])

        return db.Key.from_path(cls.kind(), '.'.join(key_list))
