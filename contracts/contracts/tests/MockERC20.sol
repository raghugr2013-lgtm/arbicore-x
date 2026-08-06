// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import {Test} from "forge-std/Test.sol";
import {IERC20} from "../interfaces/IERC20.sol";

/// @notice Minimal mintable/burnable ERC-20 used by every unit test.
///         Deliberately compact — no permit, no events other than
///         Transfer/Approval, exactly enough surface for the executor.
contract MockERC20 is IERC20 {
    string public name;
    string public symbol;
    uint8  public override decimals;
    uint256 public totalSupply;

    mapping(address => uint256) private _bal;
    mapping(address => mapping(address => uint256)) private _all;

    event Transfer(address indexed from, address indexed to, uint256 value);
    event Approval(address indexed owner, address indexed spender, uint256 value);

    constructor(string memory _name, string memory _symbol, uint8 _decimals) {
        name = _name;
        symbol = _symbol;
        decimals = _decimals;
    }

    function mint(address to, uint256 amount) external {
        _bal[to] += amount;
        totalSupply += amount;
        emit Transfer(address(0), to, amount);
    }

    function burn(address from, uint256 amount) external {
        _bal[from] -= amount;
        totalSupply -= amount;
        emit Transfer(from, address(0), amount);
    }

    function balanceOf(address a) external view override returns (uint256) { return _bal[a]; }
    function allowance(address o, address s) external view override returns (uint256) { return _all[o][s]; }

    function transfer(address to, uint256 v) external override returns (bool) {
        _bal[msg.sender] -= v;
        _bal[to] += v;
        emit Transfer(msg.sender, to, v);
        return true;
    }
    function transferFrom(address from, address to, uint256 v) external override returns (bool) {
        uint256 al = _all[from][msg.sender];
        require(al >= v, "MockERC20: allowance");
        if (al != type(uint256).max) _all[from][msg.sender] = al - v;
        _bal[from] -= v;
        _bal[to] += v;
        emit Transfer(from, to, v);
        return true;
    }
    function approve(address s, uint256 v) external override returns (bool) {
        _all[msg.sender][s] = v;
        emit Approval(msg.sender, s, v);
        return true;
    }
}
