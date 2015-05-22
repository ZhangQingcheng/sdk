// Copyright (c) 2015, the Dart project authors.  Please see the AUTHORS file
// for details. All rights reserved. Use of this source code is governed by a
// BSD-style license that can be found in the LICENSE file.

// Library used by conditional_property_assignment_test.dart,
// conditional_property_access_test.dart, and
// conditional_method_invocation_test.dart, all of which import it using the
// prefix "h.".

library lib;

var topLevelVar;

void topLevelFunction() {}

class C {
  static var staticField;
  static void staticMethod() {}
}
