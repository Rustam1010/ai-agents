import {test} from "node:test";
import assert from "node:assert/strict";
import {fileURLToPath} from "node:url";
import {experimental_scanPublicSdkOnly} from "@get-bb/plugin-sdk/testing";

test("plugin uses public SDK surfaces and declared document libraries",()=>{
 const result=experimental_scanPublicSdkOnly(fileURLToPath(new URL("../",import.meta.url)),{allow:[/^(react|fflate|pdfkit|unpdf)$/]});
 assert.deepEqual(result.privateDependencies,[]);
 assert.deepEqual(result.violations,[]);
});
