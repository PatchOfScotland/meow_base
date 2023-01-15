
import inspect
import sys

from typing import Any, Union

from core.correctness.vars import VALID_RECIPE_NAME_CHARS, \
    VALID_PATTERN_NAME_CHARS, VALID_RULE_NAME_CHARS, VALID_CHANNELS, \
    get_drt_imp_msg
from core.correctness.validation import valid_string, check_type, \
    check_implementation, valid_list, valid_dict
from core.functionality import generate_id


class BaseRecipe:
    name:str
    recipe:Any
    parameters:dict[str, Any]
    requirements:dict[str, Any]
    def __init__(self, name:str, recipe:Any, parameters:dict[str,Any]={}, 
            requirements:dict[str,Any]={}):
        check_implementation(type(self)._is_valid_recipe, BaseRecipe)
        check_implementation(type(self)._is_valid_parameters, BaseRecipe)
        check_implementation(type(self)._is_valid_requirements, BaseRecipe)
        self._is_valid_name(name)
        self.name = name
        self._is_valid_recipe(recipe)
        self.recipe = recipe
        self._is_valid_parameters(parameters)
        self.parameters = parameters
        self._is_valid_requirements(requirements)
        self.requirements = requirements

    def __new__(cls, *args, **kwargs):
        if cls is BaseRecipe:
            msg = get_drt_imp_msg(BaseRecipe)
            raise TypeError(msg)
        return object.__new__(cls)

    def _is_valid_name(self, name:str)->None:
        valid_string(name, VALID_RECIPE_NAME_CHARS)

    def _is_valid_recipe(self, recipe:Any)->None:
        pass

    def _is_valid_parameters(self, parameters:Any)->None:
        pass

    def _is_valid_requirements(self, requirements:Any)->None:
        pass


class BasePattern:
    name:str
    recipe:str
    parameters:dict[str,Any]
    outputs:dict[str,Any]
    def __init__(self, name:str, recipe:str, parameters:dict[str,Any]={}, 
            outputs:dict[str,Any]={}):
        check_implementation(type(self)._is_valid_recipe, BasePattern)
        check_implementation(type(self)._is_valid_parameters, BasePattern)
        check_implementation(type(self)._is_valid_output, BasePattern)
        self._is_valid_name(name)
        self.name = name
        self._is_valid_recipe(recipe)
        self.recipe = recipe
        self._is_valid_parameters(parameters)
        self.parameters = parameters
        self._is_valid_output(outputs)
        self.outputs = outputs

    def __new__(cls, *args, **kwargs):
        if cls is BasePattern:
            msg = get_drt_imp_msg(BasePattern)
            raise TypeError(msg)
        return object.__new__(cls)

    def _is_valid_name(self, name:str)->None:
        valid_string(name, VALID_PATTERN_NAME_CHARS)

    def _is_valid_recipe(self, recipe:Any)->None:
        pass

    def _is_valid_parameters(self, parameters:Any)->None:
        pass

    def _is_valid_output(self, outputs:Any)->None:
        pass


class BaseRule:
    name:str
    pattern:BasePattern
    recipe:BaseRecipe
    pattern_type:str=""
    recipe_type:str=""
    def __init__(self, name:str, pattern:BasePattern, recipe:BaseRecipe):
        check_implementation(type(self)._is_valid_pattern, BaseRule)
        check_implementation(type(self)._is_valid_recipe, BaseRule)
        self._is_valid_name(name)
        self.name = name
        self._is_valid_pattern(pattern)
        self.pattern = pattern
        self._is_valid_recipe(recipe)
        self.recipe = recipe
        self.__check_types_set()

    def __new__(cls, *args, **kwargs):
        if cls is BaseRule:
            msg = get_drt_imp_msg(BaseRule)
            raise TypeError(msg)
        return object.__new__(cls)

    def _is_valid_name(self, name:str)->None:
        valid_string(name, VALID_RULE_NAME_CHARS)

    def _is_valid_pattern(self, pattern:Any)->None:
        pass

    def _is_valid_recipe(self, recipe:Any)->None:
        pass

    def __check_types_set(self)->None:
        if self.pattern_type == "":
            raise AttributeError(f"Rule Class '{self.__class__.__name__}' "
                "does not set a pattern_type.")
        if self.recipe_type == "":
            raise AttributeError(f"Rule Class '{self.__class__.__name__}' "
                "does not set a recipe_type.")


class BaseMonitor:
    rules: dict[str, BaseRule]
    to_runner: VALID_CHANNELS
    def __init__(self, rules:dict[str,BaseRule])->None:
        check_implementation(type(self).start, BaseMonitor)
        check_implementation(type(self).stop, BaseMonitor)
        check_implementation(type(self)._is_valid_rules, BaseMonitor)
        self._is_valid_rules(rules)
        self.rules = rules
        
    def __new__(cls, *args, **kwargs):
        if cls is BaseMonitor:
            msg = get_drt_imp_msg(BaseMonitor)
            raise TypeError(msg)
        return object.__new__(cls)

    def _is_valid_rules(self, rules:dict[str,BaseRule])->None:
        pass

    def start(self)->None:
        pass

    def stop(self)->None:
        pass


class BaseHandler:
    def __init__(self) -> None:
        check_implementation(type(self).handle, BaseHandler)
        check_implementation(type(self).valid_event_types, BaseHandler)

    def __new__(cls, *args, **kwargs):
        if cls is BaseHandler:
            msg = get_drt_imp_msg(BaseHandler)
            raise TypeError(msg)
        return object.__new__(cls)

    def valid_event_types(self)->list[str]:
        pass

    def handle(self, event:Any)->None:
        pass


def create_rules(patterns:Union[dict[str,BasePattern],list[BasePattern]], 
        recipes:Union[dict[str,BaseRecipe],list[BaseRecipe]],
        new_rules:list[BaseRule]=[])->dict[str,BaseRule]:
    check_type(patterns, dict, alt_types=[list])
    check_type(recipes, dict, alt_types=[list])
    valid_list(new_rules, BaseRule, min_length=0)

    if isinstance(patterns, list):
        valid_list(patterns, BasePattern, min_length=0)
        patterns = {pattern.name:pattern for pattern in patterns}
    else:
        valid_dict(patterns, str, BasePattern, strict=False, min_length=0)
        for k, v in patterns.items():
            if k != v.name:
                raise KeyError(
                    f"Key '{k}' indexes unexpected Pattern '{v.name}' "
                    "Pattern dictionaries must be keyed with the name of the "
                    "Pattern.")

    if isinstance(recipes, list):
        valid_list(recipes, BaseRecipe, min_length=0)
        recipes = {recipe.name:recipe for recipe in recipes}
    else:
        valid_dict(recipes, str, BaseRecipe, strict=False, min_length=0)
        for k, v in recipes.items():
            if k != v.name:
                raise KeyError(
                    f"Key '{k}' indexes unexpected Recipe '{v.name}' "
                    "Recipe dictionaries must be keyed with the name of the "
                    "Recipe.")

    # Imported here to avoid circular imports at top of file
    import rules
    rules = {}
    all_rules ={(r.pattern_type, r.recipe_type):r for r in [r[1] \
        for r in inspect.getmembers(sys.modules["rules"], inspect.isclass) \
        if (issubclass(r[1], BaseRule))]}

    for pattern in patterns.values():
        if pattern.recipe in recipes:
            key = (type(pattern).__name__, 
                type(recipes[pattern.recipe]).__name__)
            if (key) in all_rules:
                rule = all_rules[key](
                    generate_id(prefix="Rule_"), 
                    pattern, 
                    recipes[pattern.recipe]
                )
                rules[rule.name] = rule
    return rules
